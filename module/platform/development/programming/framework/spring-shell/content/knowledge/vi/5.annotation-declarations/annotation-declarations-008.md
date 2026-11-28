# Cơ chế khám phá lệnh tự động trong ứng dụng Spring Boot 4.x

Spring Shell 4 tích hợp với Spring Boot theo cách quen thuộc của hệ sinh thái Spring: ứng dụng khai báo command trong các Spring bean, còn auto-configuration của Spring Shell tự phát hiện và đăng ký các command đó. Khi dùng Spring Boot 4.x cùng Spring Shell 4.x, bạn không cần thêm `@EnableCommand` hoặc `@CommandScan` vào lớp cấu hình.

Điểm cần hiểu rõ là **khám phá command vẫn phụ thuộc vào việc Spring tạo được bean chứa command**. Spring Shell tự động bật cơ chế đăng ký command, nhưng nó không biến mọi class trong project thành Spring bean. Một class chứa method `@Command` phải nằm trong phạm vi component scan hoặc được khai báo thành bean bằng một cách khác. Bài viết đi qua từng lớp của quá trình này, từ dependency và package layout đến `CommandRegistry`, cách tổ chức command và cách tìm lỗi khi command không xuất hiện.

## 1. Khám phá command gồm những bước nào?

Trong một ứng dụng Spring Boot 4.x dùng Spring Shell 4.x, quá trình có thể hình dung như sau:

```text
SpringApplication khởi động
        |
        v
Spring Boot component scan tìm Spring bean
        |
        v
Tạo bean chứa các method @Command
        |
        v
Spring Shell auto-configuration bật command discovery
        |
        v
Phát hiện method @Command trên các bean trong ApplicationContext
        |
        v
Đăng ký command vào CommandRegistry
        |
        v
ShellRunner nhận lệnh, help và thực thi command
```

Hai cơ chế tham gia vào đây có nhiệm vụ khác nhau:

1. **Spring Boot component scanning** tìm class được đánh dấu bằng stereotype như `@Component`, `@Service` hoặc `@Configuration` trong phạm vi package được quét, sau đó tạo bean trong `ApplicationContext`.
2. **Spring Shell command discovery** tìm các method có `@Command` trên những bean phù hợp trong context và đưa command vào `CommandRegistry`.

Vì vậy, chỉ thêm `@Command` vào một method trong class Java thông thường là chưa đủ. Nếu class đó không trở thành Spring bean, Spring Shell không có bean để khám phá method.

## 2. Điều kiện nền tảng: Spring Boot và Spring Shell 4

Spring Shell 4 dựa trên Spring Framework 7 và yêu cầu Spring Boot 4 trở lên khi tích hợp theo mô hình Spring Boot. Module `spring-shell-core` không còn phụ thuộc trực tiếp vào Spring Boot. Ứng dụng Boot cần một Spring Shell starter hoặc dependency `spring-shell-core-autoconfigure` để có phần tích hợp tự động.

Ví dụ dependency Maven cơ bản:

```xml
<properties>
    <spring-shell.version>4.0.4</spring-shell.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.shell</groupId>
        <artifactId>spring-shell-starter</artifactId>
        <version>${spring-shell.version}</version>
    </dependency>
</dependencies>
```

`spring-shell-starter` cung cấp các module Spring Shell cơ bản và tích hợp Spring Boot. Các starter của Spring Shell cũng đưa `spring-boot-starter` vào dependency graph, vì vậy không cần khai báo thêm starter Boot chỉ vì đã dùng Spring Shell starter.

Nếu ứng dụng cần terminal dựa trên JLine với provider cụ thể, chọn starter tương ứng như `spring-shell-starter-jansi`, `spring-shell-starter-jni` hoặc `spring-shell-starter-jna`. Starter `spring-shell-starter-ffm` yêu cầu JDK 22 trở lên. Chọn một starter phù hợp với terminal runtime của ứng dụng; việc chọn provider không làm thay đổi nguyên tắc khám phá command bằng Spring bean và annotation.

## 3. Đặt lớp ứng dụng ở package gốc

`@SpringBootApplication` bao gồm component scanning. Theo mặc định, package của class có annotation này là package gốc để tìm các component trong package đó và các package con.

Ví dụ cấu trúc project:

```text
com.example.catalog
├── CatalogApplication.java
├── command
│   ├── ProductCommands.java
│   └── ReportCommands.java
├── service
│   ├── ProductService.java
│   └── ReportService.java
└── config
    └── CatalogConfiguration.java
```

Lớp khởi động:

```java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
```

Vì `CatalogApplication` nằm trong `com.example.catalog`, component scan mặc định bao phủ các package con như `com.example.catalog.command` và `com.example.catalog.service`. Khi các class command được đánh dấu `@Component`, Spring có thể tạo bean cho chúng.

Không nên đặt class khởi động trong một package quá sâu, ví dụ `com.example.catalog.bootstrap`, nếu các command nằm ở package ngang hàng `com.example.catalog.command`. Package `command` khi đó không phải package con của `bootstrap` và có thể nằm ngoài phạm vi scan mặc định.

### Khi command nằm ngoài package gốc

Nếu command được đặt trong package khác, mở rộng component scan một cách có chủ đích:

```java
@SpringBootApplication(scanBasePackages = {
        "com.example.catalog",
        "com.example.shared.commands"
})
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
```

`scanBasePackages` điều chỉnh phạm vi component scan cho các component nói chung, không phải tùy chọn chỉ dành riêng cho Spring Shell. Hãy chọn package đủ hẹp để tránh vô tình khởi tạo component từ các module không thuộc ứng dụng.

## 4. Khai báo command bằng annotation

Trong Spring Shell 4, `@Command` được đặt trên method. Class khai báo các method này phải là Spring bean, thường dùng `@Component` hoặc một stereotype phù hợp như `@Service`.

Ví dụ một command class:

```java
package com.example.catalog.command;

import com.example.catalog.service.ProductService;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class ProductCommands {

    private final ProductService productService;

    public ProductCommands(ProductService productService) {
        this.productService = productService;
    }

    @Command(name = "product-list", description = "List products")
    public String list(
            @Option(longName = "category", description = "Product category")
            String category) {
        return productService.list(category).toString();
    }
}
```

Ở đây có hai loại annotation với hai nhiệm vụ khác nhau:

- `@Component` yêu cầu Spring quản lý `ProductCommands` như một bean.
- `@Command` đánh dấu method `list` là một command ứng viên để Spring Shell đăng ký.

`@Option` mô tả tham số có tên của command. Phần khai báo argument và option chi tiết được trình bày ở bài về cú pháp command; trong bài này, điều cần nhớ là các annotation tham số chỉ có tác dụng khi method đã được nhận diện như một command.

Khi người dùng gọi:

```text
product-list --category=books
```

Spring Shell tìm command `product-list`, bind `books` vào tham số `category`, sau đó gọi method trên bean `ProductCommands` đã được Spring tạo. Giá trị method trả về được ghi ra output của shell.

### Tên command mặc định

Thuộc tính `name` của `@Command` là tùy chọn. Nếu bỏ qua, Spring Shell dùng tên method làm tên command. Ví dụ:

```java
@Command(description = "Show the application version")
public String version() {
    return "Catalog CLI 1.0";
}
```

Command có tên `version`. Dù dùng tên mặc định hay tên tường minh, nên chọn cách đặt tên nhất quán và dễ hiểu trong giao diện CLI. Với command được gọi từ script, tên tường minh thường giúp giảm rủi ro khi đổi tên method Java.

## 5. Spring Boot 4 tự bật command discovery

Trong ứng dụng Spring Boot 4, Spring Shell auto-configuration tự bật cơ chế khám phá các class có method `@Command`. Bạn chỉ cần khai báo Spring bean và annotation trên method. Không cần thêm cấu hình sau:

```java
@EnableCommand(ProductCommands.class)
```

Bạn cũng không cần `@CommandScan`. Annotation `@CommandScan` thuộc mô hình đăng ký của các dòng Spring Shell 3 và đã bị loại bỏ trong Spring Shell 4. Migration guide của dự án xác nhận command scanning được tự động bật khi sử dụng Spring Boot.

Ví dụ đầy đủ tối thiểu:

```java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.shell.core.command.annotation.Command;

@SpringBootApplication
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }

    @Command(name = "hello", description = "Print a greeting")
    public String hello() {
        return "Hello from Spring Shell";
    }
}
```

Class `CatalogApplication` là configuration class và cũng được Spring Boot đăng ký trong context. Vì vậy, method `hello` là một command có thể được phát hiện. Trong ứng dụng lớn hơn, nên tách command ra các class `@Component` chuyên trách để tổ chức code và dependency rõ ràng.

## 6. Phân biệt Spring Boot component scan và Spring Shell command discovery

Hai bước này thường bị hiểu nhầm là một. Bảng sau chỉ ra vai trò của từng bước:

| Câu hỏi | Spring Boot component scan | Spring Shell command discovery |
|---|---|---|
| Tìm gì? | Class cần đăng ký thành Spring bean | Method `@Command` trên các bean phù hợp |
| Dựa vào đâu? | Package scan và stereotype như `@Component`, `@Service`, `@Configuration` | Annotation command và auto-configuration Spring Shell |
| Kết quả | Bean trong `ApplicationContext` | Command đã đăng ký trong `CommandRegistry` |
| Lỗi điển hình | Class command nằm ngoài package scan hoặc bị exclude | Bean có tồn tại nhưng method không được đánh dấu đúng hoặc tên command xung đột |

Ví dụ, class sau có `@Command` nhưng không có stereotype và không được khai báo bằng `@Bean`:

```java
public class HiddenCommands {

    @Command(name = "hidden")
    public String hidden() {
        return "You cannot invoke this command yet";
    }
}
```

Nếu không có cấu hình nào tạo bean `HiddenCommands`, method `hidden` sẽ không xuất hiện như một command trong Spring Shell. Sửa bằng cách khai báo bean:

```java
@Component
public class HiddenCommands {
    // command methods
}
```

Hoặc khai báo bean tường minh trong configuration class:

```java
@Configuration
public class CommandConfiguration {

    @Bean
    HiddenCommands hiddenCommands() {
        return new HiddenCommands();
    }
}
```

Trong trường hợp dùng `@Bean`, class vẫn phải được tạo trong context; Spring Shell có thể khám phá các method command trên bean đó.

## 7. Tổ chức command theo nhóm

Khi CLI có nhiều command, có thể dùng `@CommandGroup` để đặt prefix và tên nhóm chung cho các command trong một class. `@CommandGroup` là annotation cấp class; các method bên trong tiếp tục dùng `@Command`.

```java
package com.example.catalog.command;

import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.CommandGroup;
import org.springframework.stereotype.Component;

@Component
@CommandGroup(
        name = "Product Commands",
        prefix = "product"
)
public class ProductCommands {

    @Command(name = "list", description = "List products")
    public String list() {
        return "Product list";
    }

    @Command(name = "count", description = "Count products")
    public int count() {
        return 42;
    }
}
```

Hai command có thể được gọi bằng:

```text
product list
product count
```

`name` trong `@CommandGroup` là tên nhóm hiển thị trong trợ giúp; `prefix` tạo tiền tố chung cho tên command. Nếu một method có `group` riêng trong `@Command`, giá trị group của method được ưu tiên cho method đó. Việc gom nhóm giúp kết quả `help` dễ đọc khi ứng dụng có nhiều chức năng.

## 8. Command Registry và cách đăng ký bằng code

`CommandRegistry` là nơi lưu các command mà shell biết. Theo mặc định, Spring Shell đưa các command được định nghĩa trong application context vào registry. Có thể đăng ký hoặc hủy đăng ký command động thông qua registry khi ứng dụng cần thay đổi command theo trạng thái hoặc module được nạp.

Ngoài annotation, Spring Shell 4 hỗ trợ mô hình lập trình trực tiếp. Một bean có kiểu `Command` cũng được tự động đăng ký trong Spring Shell 4:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.Command;

@Configuration
public class ProgrammaticCommands {

    @Bean
    Command healthCommand() {
        return Command.builder()
                .name("health-check")
                .execute(context -> {
                    context.outputWriter().println("Application is healthy");
                });
    }
}
```

Mô hình annotation phù hợp với command có method Java, dependency injection và tham số được bind từ annotation. Mô hình programmatic hữu ích khi command được tạo từ cấu hình hoặc cần lắp ghép logic thực thi linh hoạt. Cả hai mô hình đều kết thúc ở `CommandRegistry`.

## 9. Nếu không dùng Spring Boot

Tự động bật command discovery là hành vi tích hợp của Spring Boot. Với ứng dụng Spring Framework thuần, không có Boot auto-configuration, bạn phải bật cơ chế đăng ký command bằng `@EnableCommand` trên configuration class và chỉ định các class chứa method `@Command`.

Ví dụ:

```java
@Configuration
@EnableCommand(ProductCommands.class)
public class ShellConfiguration {
}
```

Trong ứng dụng không dùng Boot, vẫn phải tạo các dependency và bean cần thiết cho Spring Shell, rồi lấy `ShellRunner` từ context để chạy shell. `@EnableCommand` giúp Spring Shell biết những class nào cần xử lý annotation. Không mang cấu hình này sang ứng dụng Spring Boot 4 chỉ vì thấy ví dụ cũ trên mạng; trong Boot, auto-configuration đã đảm nhiệm bước đó.

## 10. Khác biệt khi nâng từ Spring Shell 3 lên 4

Nếu chuyển một ứng dụng từ Spring Shell 3 sang 4, cần rà lại cả annotation và cơ chế đăng ký:

| Spring Shell 3 | Spring Shell 4 trong Spring Boot |
|---|---|
| Có thể cần `@EnableCommand` hoặc `@CommandScan` để bật command discovery | Command scanning tự động được bật bởi Spring Boot integration |
| `@CommandScan` có thể chỉ định package quét | `@CommandScan` đã bị loại bỏ |
| `@Command` có thể được dùng ở cấp class để đặt prefix/default trong một số API 3.x | `@Command` chỉ đặt trên method; dùng `@CommandGroup` để gom command ở cấp class |
| Annotation cũ như `@ShellComponent`, `@ShellMethod`, `@ShellOption` từng được dùng trong legacy API | Các annotation legacy này đã bị loại bỏ; dùng `@Command`, `@Option`, `@Argument` mới |

Spring Shell 4 chuyển các annotation mới vào package `org.springframework.shell.core.command.annotation`. Khi migrate, hãy cập nhật import và cấu trúc class command theo tài liệu v4. Đồng thời, Spring Shell 4 yêu cầu Spring Boot 4+ khi tích hợp Boot; không thể chỉ nâng riêng Spring Shell 4 trong một ứng dụng vẫn dùng Spring Boot 3.x.

## 11. Chẩn đoán khi command không được phát hiện

Khi command không xuất hiện trong trợ giúp hoặc báo không tìm thấy lệnh, hãy kiểm tra theo thứ tự từ Spring container đến Spring Shell:

1. **Kiểm tra dependency:** ứng dụng đã dùng Spring Shell starter hoặc `spring-shell-core-autoconfigure` tương ứng với Boot 4 chưa? Chỉ có `spring-shell-core` thì chưa đủ phần tích hợp Boot.
2. **Kiểm tra component scan:** package của class command có nằm dưới package gốc của `@SpringBootApplication` hoặc trong `scanBasePackages` không?
3. **Kiểm tra bean:** class command có `@Component`, `@Service` hoặc được tạo bằng `@Bean` không? Bean có bị `@Profile`, `@Conditional` hoặc cấu hình khác loại khỏi context không?
4. **Kiểm tra filter:** class command có bị `excludeFilters` trong `@ComponentScan` loại bỏ không?
5. **Kiểm tra annotation:** method có dùng `org.springframework.shell.core.command.annotation.Command` đúng package của Spring Shell 4 không? `@Command` trong v4 phải nằm trên method.
6. **Kiểm tra tên và nhóm:** command có tên rõ ràng không, có trùng tên hoặc alias với command khác không, prefix của `@CommandGroup` có đúng cách gọi không?
7. **Kiểm tra registry và shell mode:** command có được đăng ký vào context và shell đang chạy đúng `ShellRunner`/mode không? Dùng lệnh `help` hoặc `help <command>` để kiểm tra danh sách và mô tả command.

Có thể bật log debug khi khởi động để quan sát auto-configuration và điều kiện cấu hình:

```bash
java -jar catalog-cli.jar --debug
```

Hoặc đặt trong `application.yml`:

```yaml
debug: true
```

Đọc condition evaluation report để xác định auto-configuration có được áp dụng hay bị loại bởi điều kiện nào. Lưu ý `--debug` là tham số cấu hình Spring Boot; nếu ứng dụng có command tên hoặc option trùng, hãy phân biệt nó với cú pháp của Spring Shell.

## 12. Checklist trước khi hoàn thành khai báo command

- [ ] Đã dùng Spring Boot 4.x cùng Spring Shell 4.x tương thích.
- [ ] Đã thêm Spring Shell starter hoặc module auto-configuration cho ứng dụng Boot.
- [ ] Lớp khởi động nằm ở package gốc bao phủ các package command.
- [ ] Mỗi class command là Spring bean, thường có `@Component` hoặc `@Service`.
- [ ] Mỗi command được đánh dấu bằng `@Command` trên method.
- [ ] Không dùng `@CommandScan` hoặc thêm `@EnableCommand` không cần thiết trong ứng dụng Boot 4.
- [ ] Dùng `@CommandGroup` khi cần prefix và nhóm trợ giúp chung.
- [ ] Không loại class command khỏi component scan bằng filter hoặc điều kiện cấu hình.
- [ ] Tên command và alias không xung đột với command khác.
- [ ] Đã chạy ứng dụng, kiểm tra `help` và gọi thử từng command.

## Tài liệu tham khảo

1. [Spring Shell 4 – Command Registration](https://docs.spring.io/spring-shell/reference/commands/registration.html) – hai mô hình đăng ký, annotation-based registration và `CommandRegistry`.
2. [Spring Shell 4 – v4 Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide) – tự động bật command scanning trong Spring Boot 4, các annotation bị loại bỏ và thay đổi module.
3. [Spring Boot – Structuring Your Code](https://docs.spring.io/spring-boot/reference/using/structuring-your-code.html) – package gốc và phạm vi component scan của `@SpringBootApplication`.
4. [Spring Shell 4 – Building](https://docs.spring.io/spring-shell/reference/building.html) – starter, terminal provider và dependency cho ứng dụng Spring Shell.
5. [Spring Shell 4 – Organizing Commands](https://docs.spring.io/spring-shell/reference/commands/organize.html) – `@CommandGroup`, group và prefix.
6. [Spring Shell 4 – Command Syntax](https://docs.spring.io/spring-shell/reference/commands/syntax.html) – annotation cho argument và option của command.

Khi cần tìm nguyên nhân một command không xuất hiện, hãy xác minh trước tiên class command có thực sự là bean trong `ApplicationContext` hay không. Khi bean đã tồn tại, mới tiếp tục kiểm tra annotation và quá trình đăng ký vào `CommandRegistry`. Cách kiểm tra theo thứ tự này giúp khoanh vùng chính xác lớp chịu trách nhiệm trong cơ chế khám phá tự động của Spring Shell 4.
