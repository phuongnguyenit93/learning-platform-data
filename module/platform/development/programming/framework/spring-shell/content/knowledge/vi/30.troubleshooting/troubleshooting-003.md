# Trùng command, tiền tố hoặc nhóm gây nhập nhằng

Khi ứng dụng Spring Shell có nhiều nhóm chức năng, command thường được chia vào các class, mỗi class có một tiền tố và một nhóm hiển thị trong help. Cách tổ chức này giúp command dễ tìm hơn, nhưng cũng có thể tạo ra lỗi khó hiểu: hai method đăng ký cùng một tên, alias của command này trùng với tên command khác, global prefix bị lặp với prefix của nhóm, hoặc người phát triển tưởng tên nhóm help là một phần của command path.

Để chẩn đoán đúng, hãy phân biệt ba thành phần: tên command dùng để định tuyến, alias là tên gọi thay thế, và group chỉ dùng để tổ chức help. Bài này sử dụng Spring Shell 4.0.4, trong đó có cả prefix ở cấp nhóm và global command prefix.

## 1. Phân biệt command name, alias, prefix và group

Bốn khái niệm này có vai trò khác nhau:

| Thành phần | Vai trò | Có tham gia định tuyến? |
|---|---|---|
| Command name | Tên chính mà người dùng nhập để gọi command | Có |
| Alias | Tên thay thế cho một command | Có |
| Prefix | Phần đầu được ghép vào tên command để tạo namespace | Có |
| Group | Nhãn gom command trong help và danh sách command | Không |

Ví dụ:

~~~java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.CommandGroup;

@CommandGroup(
        prefix = "customer",
        name = "Customer Management",
        description = "Quản lý khách hàng")
class CustomerCommands {

    @Command(name = "list", description = "Liệt kê khách hàng")
    public String list() {
        return "Danh sách khách hàng";
    }

    @Command(name = "show", description = "Xem thông tin khách hàng")
    public String show() {
        return "Thông tin khách hàng";
    }
}
~~~

Tên command sau khi áp dụng prefix là:

~~~text
customer list
customer show
~~~

Cả hai command thuộc nhóm Customer Management. Người dùng nhập customer list để chạy command; họ không nhập Customer Management list.

Trong Spring Shell 4.0.4, @CommandGroup đánh dấu class là một command group và có ba thuộc tính prefix, name, description. Annotation này được giới thiệu từ 4.0.2. @Command(group = "...") ở method có thể ghi đè group mặc định của class.

## 2. Những loại xung đột thường gặp

Có thể chia lỗi nhập nhằng thành các nhóm sau:

| Loại xung đột | Ví dụ | Dấu hiệu |
|---|---|---|
| Trùng tên chính | Hai command cùng có tên customer list | Một command không được đăng ký như mong đợi hoặc registry báo lỗi |
| Alias trùng tên chính | Alias ls của command A trùng tên chính ls của command B | Cùng một trigger nhưng không xác định rõ command đích |
| Alias trùng alias | Hai command đều khai báo alias c-list | Alias có thể trỏ nhầm hoặc làm cấu hình không nhất quán |
| Prefix bị lặp | Global prefix app, group prefix app, command customer list | Người dùng phải nhập app app customer list |
| Prefix không được áp dụng | Class có group name nhưng không có prefix | Help hiển thị nhóm đúng nhưng command path không có namespace mong đợi |
| Nhầm group với prefix | Chỉ đặt group = Customer và mong command thành customer list | Help được gom nhóm nhưng command vẫn giữ tên cũ |
| Đăng ký hai lần | Một command được tạo bằng @Command và một Command bean cùng tên | Registry nhận nhiều nguồn định nghĩa cho cùng command |
| Đè group ngoài ý muốn | Method có group khác với @CommandGroup.name | Command xuất hiện dưới nhóm khác trong help |

Cần xác định lỗi thuộc nhóm nào trước khi đổi tên. Thay group label không sửa được xung đột command name; thêm prefix cũng không giải quyết được hai alias trùng nhau nếu alias vẫn giống nhau sau khi áp dụng namespace.

## 3. Hiểu quy tắc ghép prefix trong Spring Shell 4.0.4

Spring Shell 4.0.4 có hai nơi khai báo prefix:

1. Global prefix qua property spring.shell.command.prefix.
2. Prefix theo class qua @CommandGroup(prefix = "...").

Tên command được ghép theo thứ tự:

~~~text
global prefix -> command group prefix -> command name
~~~

Ví dụ cấu hình:

~~~yaml
spring:
  shell:
    command:
      prefix: acme
~~~

Và class command:

~~~java
@CommandGroup(prefix = "customer", name = "Customer Management")
class CustomerCommands {

    @Command(name = "list")
    public String list() {
        return "Danh sách khách hàng";
    }
}
~~~

Tên command cuối cùng là:

~~~text
acme customer list
~~~

Bảng sau minh họa các trường hợp:

| Global prefix | Group prefix | Command name | Tên gọi |
|---|---|---|---|
| acme | customer | list | acme customer list |
| acme | rỗng | customer list | acme customer list |
| rỗng | customer | list | customer list |
| rỗng | rỗng | customer list | customer list |

Global prefix được thêm trong Spring Shell 4.0.4. Nó áp dụng cho command người dùng khai báo bằng @Command; các command built-in như help, clear, version không bị thay đổi. Nếu dùng command đăng ký bằng Command.Builder, hãy khai báo tên đầy đủ trong builder và kiểm tra hành vi của chính cách đăng ký đó, thay vì mặc định cho rằng global prefix tự áp dụng.

## 4. Prefix bị lặp do khai báo cùng một phần ở nhiều nơi

Một lỗi phổ biến là đặt cùng một chuỗi ở global prefix, group prefix và command name:

~~~yaml
spring:
  shell:
    command:
      prefix: app
~~~

~~~java
@CommandGroup(prefix = "app", name = "Application Commands")
class ApplicationCommands {

    @Command(name = "app status")
    public String status() {
        return "OK";
    }
}
~~~

Cấu hình trên tạo ra command path có các thành phần lặp:

~~~text
app app app status
~~~

Hãy để mỗi cấp chịu trách nhiệm cho một phần:

~~~yaml
spring:
  shell:
    command:
      prefix: app
~~~

~~~java
@CommandGroup(prefix = "system", name = "System Commands")
class SystemCommands {

    @Command(name = "status")
    public String status() {
        return "OK";
    }
}
~~~

Kết quả:

~~~text
app system status
~~~

Khi chẩn đoán prefix lặp, kiểm tra lần lượt:

1. Property spring.shell.command.prefix trong tất cả nguồn cấu hình đang active.
2. @CommandGroup(prefix = ...) trên class command.
3. @Command(name = ...) trên method.
4. Command được tạo programmatically bằng Command.Builder.name(...).
5. Profile hoặc environment variable có thể ghi đè property mặc định.

Không chỉ kiểm tra application.yml; property có thể đến từ profile, biến môi trường, system property hoặc tham số khởi động.

## 5. Hai class có cùng prefix không nhất thiết là lỗi

Dùng chung prefix là cách bình thường để chia sẻ namespace. Ví dụ:

~~~java
@CommandGroup(prefix = "customer", name = "Customer Queries")
class CustomerQueryCommands {

    @Command(name = "list")
    public String list() {
        return "Danh sách khách hàng";
    }

    @Command(name = "show")
    public String show() {
        return "Chi tiết khách hàng";
    }
}
~~~

~~~java
@CommandGroup(prefix = "customer", name = "Customer Reports")
class CustomerReportCommands {

    @Command(name = "report")
    public String report() {
        return "Báo cáo khách hàng";
    }
}
~~~

Các tên command là:

~~~text
customer list
customer show
customer report
~~~

Chúng không trùng nhau. Việc hai class cùng prefix customer không gây xung đột nếu phần tên command còn lại khác nhau.

Xung đột xuất hiện khi hai định nghĩa tạo ra cùng một command name cuối cùng. Ví dụ class thứ hai cũng khai báo @Command(name = "list"), khiến cả hai cùng tạo customer list. Group label khác nhau không làm hai tên command trở nên khác nhau.

## 6. Group name không phải namespace

Hai class có thể dùng cùng group name để command xuất hiện trong cùng một nhóm help:

~~~java
@CommandGroup(prefix = "customer", name = "Customer Commands")
class CustomerQueryCommands {
    @Command(name = "list")
    public String list() {
        return "Danh sách";
    }
}
~~~

~~~java
@CommandGroup(prefix = "customer", name = "Customer Commands")
class CustomerMaintenanceCommands {
    @Command(name = "archive")
    public String archive() {
        return "Đã lưu trữ";
    }
}
~~~

Kết quả command:

~~~text
customer list
customer archive
~~~

Cả hai được gom dưới nhãn Customer Commands. Đây là hành vi mong muốn.

Nếu hai class cùng group name nhưng có prefix khác nhau, chúng vẫn có thể xuất hiện cùng nhóm help mà command path khác nhau. Group chỉ là metadata trình bày.

Ví dụ:

~~~java
@CommandGroup(prefix = "customer", name = "Administration")
class CustomerCommands { /* ... */ }

@CommandGroup(prefix = "account", name = "Administration")
class AccountCommands { /* ... */ }
~~~

Không nên đổi group name chỉ để sửa lỗi gọi command. Hãy sửa prefix hoặc command name nếu đường dẫn bị trùng.

## 7. Method-level group có thể ghi đè group của class

Một command có thể được chuyển sang nhóm hiển thị riêng bằng group trên method:

~~~java
@CommandGroup(prefix = "customer", name = "Customer Commands")
class CustomerCommands {

    @Command(name = "list")
    public String list() {
        return "Danh sách";
    }

    @Command(
            name = "export",
            group = "Data Export",
            description = "Xuất dữ liệu khách hàng")
    public String export() {
        return "Đã xuất dữ liệu";
    }
}
~~~

customer list thuộc nhóm Customer Commands; customer export thuộc nhóm Data Export. Prefix vẫn là customer.

Nếu một command xuất hiện trong nhóm help không mong đợi, kiểm tra group ở method trước. Thay đổi @CommandGroup.name không ghi đè một giá trị group đã khai báo rõ ở method.

## 8. Tên chính và alias phải có không gian tên rõ ràng

Alias là một tên khác để gọi command. Trong Spring Shell 4.0.4, alias được khai báo trên method @Command hoặc thông qua API command programmatic.

Ví dụ:

~~~java
@CommandGroup(prefix = "customer", name = "Customer Commands")
class CustomerCommands {

    @Command(name = "list", alias = {"cl", "customers"})
    public String list() {
        return "Danh sách khách hàng";
    }

    @Command(name = "show")
    public String show() {
        return "Chi tiết khách hàng";
    }
}
~~~

Tên chính là customer list; các alias được khai báo là những tên thay thế theo metadata của command. Dùng alias ngắn, dễ nhớ và có quy ước thống nhất. Khi prefix được thêm ở nhiều cấp, hãy kiểm tra tên và alias thực tế qua registry thay vì tự suy đoán cách ghép.

Không nên dùng cùng một alias cho hai command khác nhau:

~~~java
@Command(name = "list", alias = "ls")
public String listCustomers() {
    return "Danh sách khách hàng";
}

@Command(name = "list-users", alias = "ls")
public String listUsers() {
    return "Danh sách người dùng";
}
~~~

Hai command cùng khai báo alias ls. Người dùng không thể biết chắc alias đó đại diện cho thao tác nào. Đổi một alias thành tên riêng, ví dụ customer-ls và user-ls.

Cũng tránh alias trùng với tên chính của command khác. Hãy xem command name và tất cả alias như một tập trigger cần được kiểm soát thống nhất.

## 9. Trùng tên giữa annotation command và programmatic command

Spring Shell 4 hỗ trợ cả hai cách đăng ký:

- Annotation model: method @Command trong Spring bean.
- Programmatic model: bean kiểu Command, thường tạo bằng Command.Builder.

CommandRegistry được Spring tự động populate từ các command có trong application context. Vì vậy, cùng một command có thể vô tình được khai báo hai lần từ hai nguồn khác nhau.

Ví dụ:

~~~java
@Component
class CustomerCommands {

    @Command(name = "customer list")
    public String list() {
        return "Danh sách khách hàng";
    }
}
~~~

~~~java
@Configuration
class CustomerCommandConfiguration {

    @Bean
    Command customerListCommand() {
        return Command.builder()
                .name("customer list")
                .execute(context -> {
                    context.outputWriter().println("Danh sách khách hàng");
                    return ExitStatus.OK;
                });
    }
}
~~~

Cả hai cùng khai báo tên customer list. Chọn một nguồn đăng ký cho command đó hoặc đặt tên khác nếu đây là hai chức năng thực sự khác nhau.

Khi điều tra, tìm cả method @Command lẫn bean trả về Command. Đừng chỉ tìm trong package command annotation.

## 10. Dùng CommandRegistry để kiểm tra tên command đang được đăng ký

CommandRegistry cung cấp các API hữu ích:

| API | Mục đích |
|---|---|
| getCommands() | Lấy tập command đã đăng ký |
| getCommandByName(name) | Tìm command theo tên chính |
| getCommandByAlias(name) | Tìm command theo alias |
| getCommandsByPrefix(prefix) | Liệt kê command theo prefix |
| registerCommand(command) | Đăng ký command lúc runtime |
| unregisterCommand(command) | Gỡ command lúc runtime |

Javadoc nêu rõ command được nhận diện duy nhất theo tên. Khi chẩn đoán, hãy kiểm tra tên đã đăng ký thay vì chỉ đọc annotation trên source code.

Ví dụ một component chẩn đoán có thể in danh sách command ở môi trường development:

~~~java
import java.util.Comparator;

import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.Command;
import org.springframework.shell.core.command.CommandRegistry;

@Configuration
class CommandDiagnosticsConfiguration {

    @Bean
    ApplicationRunner listRegisteredCommands(CommandRegistry registry) {
        return args -> registry.getCommands().stream()
                .sorted(Comparator.comparing(Command::getName))
                .forEach(command -> System.out.printf(
                        "name=%s aliases=%s group=%s%n",
                        command.getName(),
                        command.getAliases(),
                        command.getGroup()));
    }
}
~~~

Chỉ bật component chẩn đoán này trong profile development hoặc test. Tên command và alias thường là metadata tĩnh, nhưng không cần ghi chúng ra log production ở mọi lần khởi động nếu không phục vụ vận hành.

Kiểm tra một command cụ thể:

~~~java
Command command = registry.getCommandByName("customer list");
Command aliasTarget = registry.getCommandByAlias("cl");

if (command == null) {
    throw new IllegalStateException("Không tìm thấy customer list");
}

if (aliasTarget != command) {
    throw new IllegalStateException("Alias cl không trỏ tới customer list");
}
~~~

Kiểm tra các command dưới một prefix:

~~~java
registry.getCommandsByPrefix("customer")
        .forEach(command -> System.out.println(command.getName()));
~~~

## 11. Viết kiểm tra trùng tên và alias trong test

Registry giúp xác nhận những command đã được đăng ký. Có thể thêm một kiểm tra để phát hiện trigger trùng giữa tên chính và alias:

~~~java
import java.util.HashMap;
import java.util.Map;

import org.springframework.shell.core.command.Command;
import org.springframework.shell.core.command.CommandRegistry;

static void assertNoTriggerCollisions(CommandRegistry registry) {
    Map<String, String> ownerByTrigger = new HashMap<>();

    for (Command command : registry.getCommands()) {
        claim(ownerByTrigger, command.getName(), command.getName());

        for (String alias : command.getAliases()) {
            claim(ownerByTrigger, alias, command.getName());
        }
    }
}

private static void claim(
        Map<String, String> ownerByTrigger,
        String trigger,
        String commandName) {

    String previousOwner = ownerByTrigger.putIfAbsent(trigger, commandName);

    if (previousOwner != null) {
        throw new IllegalStateException(
                "Trigger '" + trigger + "' được khai báo nhiều lần: "
                        + previousOwner + " và " + commandName);
    }
}
~~~

Kiểm tra này coi tên chính và alias là cùng một không gian trigger. Nó phát hiện alias trùng với alias khác, alias trùng tên chính và alias tự lặp trong metadata đã đăng ký.

Để phát hiện một command chính đã bị mất do xung đột trước khi test đọc registry, hãy xác nhận tập tên mong đợi:

~~~java
assertThat(registry.getCommands())
        .extracting(Command::getName)
        .containsExactlyInAnyOrder(
                "customer list",
                "customer show",
                "customer admin list");
~~~

CommandRegistry chỉ cung cấp các command cuối cùng trong registry. Một test danh sách tên mong đợi giúp phát hiện trường hợp một command dự kiến không xuất hiện sau quá trình đăng ký.

## 12. Kiểm tra global prefix và group prefix trong cấu hình

Nếu ứng dụng dùng global prefix, hãy xác nhận giá trị thực tế trong môi trường đang chạy:

~~~yaml
spring:
  shell:
    command:
      prefix: acme
~~~

Nếu profile production ghi đè thành prod, command path có thể khác với local:

~~~yaml
# application-prod.yml
spring:
  shell:
    command:
      prefix: prod
~~~

Một lỗi thường gặp là tài liệu hướng dẫn người dùng gọi acme customer list trong khi profile active tạo ra prod customer list.

Các bước kiểm tra:

1. Xác định profile active.
2. Kiểm tra spring.shell.command.prefix trong file profile.
3. Kiểm tra environment variable SPRING_SHELL_COMMAND_PREFIX.
4. Kiểm tra @CommandGroup.prefix.
5. Lấy tên cuối cùng bằng CommandRegistry.getCommands().

Đừng giả định prefix trong file mặc định là prefix đang có hiệu lực. Spring Boot có thể nhận property từ nhiều nguồn và áp dụng quy tắc override theo thứ tự ưu tiên.

## 13. Phân biệt lỗi tên command với lỗi component scan

Không phải command không tìm thấy nào cũng do trùng tên. Nếu class chứa method @Command không nằm trong Spring application context hoặc bị loại khỏi component scan, command sẽ không được đăng ký.

Spring Shell 4 yêu cầu class chứa method @Command là Spring bean. Trong Spring Boot, auto-configuration hỗ trợ command registration. Với ứng dụng không dùng Spring Boot, cần cấu hình @EnableCommand.

Ví dụ:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.shell.core.command.annotation.Command;

@Component
class CustomerCommands {

    @Command(name = "customer list")
    public String list() {
        return "Danh sách khách hàng";
    }
}
~~~

Nếu package này bị loại bởi @ComponentScan(excludeFilters = ...), command sẽ không có trong registry. Hãy xác nhận bean tồn tại và kiểm tra registry.getCommandByName(...) trước khi đổi tên command.

## 14. Tránh dùng tên built-in cho command tùy chỉnh

Spring Shell cung cấp các command tiêu chuẩn như help, clear, version, script và các command liên quan đến history/quit tùy cấu hình.

Không nên đặt tên command hoặc alias của ứng dụng trùng với các tên built-in. Nếu người dùng gõ help, họ nên nhận được chức năng trợ giúp chuẩn; không phải một command nghiệp vụ tình cờ có cùng tên.

Nếu cần một chức năng trợ giúp riêng cho domain, dùng namespace rõ ràng:

~~~java
@Command(name = "customer help", description = "Trợ giúp các thao tác khách hàng")
public String customerHelp() {
    return "Hướng dẫn quản lý khách hàng";
}
~~~

Không đổi tên built-in chỉ để tránh một command tùy chỉnh trùng tên. Hãy đặt tên riêng cho command của ứng dụng.

## 15. Nhập nhằng do command path quá giống nhau

Ngay cả khi tên command không trùng hoàn toàn, các command có cấu trúc quá giống nhau vẫn dễ khiến người dùng chọn nhầm:

~~~text
customer list
customer-list
customers list
customer ls
~~~

Các tên trên có ý nghĩa gần nhau nhưng không theo cùng một quy ước. Hãy chọn một cấu trúc nhất quán:

~~~text
customer list
customer show
customer create
customer update
customer delete
~~~

Một số nguyên tắc đặt tên:

- Dùng danh từ làm namespace, động từ làm hành động.
- Dùng một kiểu phân tách từ thống nhất.
- Không tạo nhiều command chỉ khác nhau một ký tự.
- Dùng alias để hỗ trợ tương thích ngược, không dùng alias làm tên command chính mới.
- Giữ tên command ngắn nhưng đủ phân biệt chức năng.

## 16. Nhập nhằng giữa command path, option và positional argument

Spring Shell phân tích command name, subcommand name, option và argument theo cú pháp riêng. Options và arguments có thể xuất hiện theo nhiều thứ tự; argument là vị trí, còn option có tên.

Ví dụ:

~~~text
customer import --file customers.csv
customer import customers.csv
~~~

Hai cách gọi có thể tương ứng với các cách khai báo input khác nhau. Nếu command có nhiều positional argument hoặc nhiều subcommand, người dùng dễ nhầm token nào thuộc command path và token nào là dữ liệu.

Ưu tiên named options cho input quan trọng:

~~~text
customer import --file customers.csv --mode replace
~~~

Thay vì yêu cầu người dùng nhớ thứ tự:

~~~text
customer import customers.csv replace
~~~

Spring Shell 4 hỗ trợ option dạng --key=value, --key value, -k=value và -k value. Short options không thể nhóm thành -abc. Dùng help <command> để xem SYNOPSIS và danh sách option/argument của từng command.

## 17. Cách chẩn đoán một lỗi command cụ thể

Khi người dùng báo customer list không chạy hoặc chạy nhầm command, thực hiện theo thứ tự:

1. Ghi lại chính xác dòng lệnh họ nhập, gồm cả dấu nháy và option.
2. Chạy help để xem tên command và group hiện có.
3. Chạy help customer list để xem help của command cụ thể.
4. Kiểm tra global prefix trong environment và profile active.
5. Kiểm tra @CommandGroup.prefix của class.
6. Kiểm tra @Command.name và alias của method.
7. Kiểm tra các command programmatic được đăng ký bằng Command.Builder.
8. Dùng CommandRegistry.getCommandByName, getCommandByAlias và getCommandsByPrefix.
9. Kiểm tra component scan và @EnableCommand nếu command không có trong registry.
10. Viết test xác nhận command name, alias và output sau khi sửa.

Đừng đổi đồng thời prefix, command name và group name trong một lần sửa nếu chưa xác định được trường nào gây lỗi. Sửa một nguyên nhân, chạy lại command và kiểm tra help output để biết thay đổi đã giải quyết đúng vấn đề chưa.

## 18. Bảng triệu chứng và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Command không xuất hiện trong help | Bean không được scan hoặc command chưa đăng ký | Kiểm tra Spring bean, component scan và @EnableCommand |
| Hai command có cùng tên | Hai method hoặc hai nguồn registration tạo cùng command name | Đổi prefix/name hoặc bỏ một định nghĩa trùng |
| Alias gọi nhầm command | Alias trùng alias hoặc trùng tên chính khác | Tạo alias duy nhất và kiểm tra registry |
| Command yêu cầu prefix bị lặp | Global prefix, group prefix và method name chứa cùng segment | Chỉ khai báo mỗi segment ở một cấp |
| Help hiển thị nhóm sai | Method-level group ghi đè group class | Kiểm tra @Command(group = ...) |
| Hai nhóm help có cùng tên | Các command được cố ý gom vào cùng nhãn hoặc đặt nhầm group | Xác nhận mục đích grouping; group trùng không đồng nghĩa command trùng |
| Command có tên gần giống gây chọn nhầm | Quy ước đặt tên thiếu nhất quán | Chuẩn hóa namespace và động từ |
| Command chạy local nhưng không chạy production | Profile hoặc global prefix khác nhau | Kiểm tra property hiệu lực và command registry ở production |
| Command annotation và programmatic command xung đột | Cùng chức năng được đăng ký từ hai nguồn | Chỉ giữ một nguồn hoặc dùng tên riêng |
| Command có trong registry nhưng không chạy được | Availability hoặc lỗi parse/option | Kiểm tra availability, help, options và arguments |

## 19. Bài tập thực hành

Ứng dụng có các command quản lý khách hàng và người dùng. Sau khi bổ sung global prefix, một số command không còn chạy đúng.

Cấu hình hiện tại:

~~~yaml
spring:
  shell:
    command:
      prefix: acme
~~~

Hai class command:

~~~java
@CommandGroup(prefix = "customer", name = "Customer Commands")
class CustomerCommands {

    @Command(name = "list", alias = "ls")
    public String list() {
        return "Customers";
    }
}

@CommandGroup(prefix = "customer", name = "Customer Admin")
class CustomerAdminCommands {

    @Command(name = "list", alias = "ls")
    public String list() {
        return "Customer administration";
    }
}
~~~

Hãy thực hiện:

1. Xác định command path cuối cùng sau khi áp dụng global prefix và group prefix.
2. Tìm xung đột giữa hai command name.
3. Tìm xung đột alias.
4. Giữ namespace acme customer cho thao tác truy vấn.
5. Đổi namespace quản trị thành acme customer admin.
6. Đặt alias riêng cho từng command.
7. Xác nhận group name chỉ ảnh hưởng đến help.
8. Dùng CommandRegistry kiểm tra tên chính, alias và prefix.
9. Viết test xác nhận cả hai command xuất hiện và chạy đúng.
10. Kiểm tra help output để bảo đảm command nằm trong nhóm mong đợi.

Kết quả cần nộp: bảng tên command trước/sau, hai class đã sửa, cấu hình global prefix, test registry và output help sau khi sửa.

## 20. Checklist trước khi phát hành command mới

- [ ] Mỗi command có một tên chính duy nhất.
- [ ] Alias không trùng tên chính của command khác.
- [ ] Alias không trùng alias của command khác.
- [ ] Global prefix đã được kiểm tra trong profile đang chạy.
- [ ] Group prefix không lặp với global prefix.
- [ ] Method command name không lặp lại prefix đã khai báo.
- [ ] @CommandGroup.name và @Command.group chỉ dùng để tổ chức help.
- [ ] Method-level group override được khai báo có chủ đích.
- [ ] Không dùng tên built-in cho command tùy chỉnh.
- [ ] Command annotation và programmatic registration không định nghĩa trùng.
- [ ] Command class là Spring bean và nằm trong phạm vi scan.
- [ ] Registry có đủ các command dự kiến.
- [ ] Test xác nhận tên chính, alias và command path.
- [ ] Help output phản ánh đúng group và description.
- [ ] Option và positional argument được thiết kế rõ ràng.

## Tài liệu tham khảo

- [Spring Shell 4.0.4 — Command Registration](https://docs.spring.io/spring-shell/reference/commands/registration.html)
- [Spring Shell 4.0.4 — Organizing Commands](https://docs.spring.io/spring-shell/reference/commands/organize.html)
- [Spring Shell 4.0.4 — Command Syntax](https://docs.spring.io/spring-shell/reference/commands/syntax.html)
- [Spring Shell 4.0.4 API — CommandRegistry](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/CommandRegistry.html)
- [Spring Shell 4.0.4 API — Command](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/Command.html)
- [Spring Shell 4.0.4 API — CommandGroup](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/CommandGroup.html)
- [Spring Shell 4.0.4 API — @Command](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Command.html)
- [Spring Shell 4.0.4 Release Notes](https://github.com/spring-projects/spring-shell/releases)
- [Spring Shell PR #1360 — Global command prefix](https://github.com/spring-projects/spring-shell/pull/1360)