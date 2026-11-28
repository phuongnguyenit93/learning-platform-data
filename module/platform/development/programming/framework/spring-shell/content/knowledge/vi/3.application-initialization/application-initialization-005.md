# Viết và chạy lệnh chào đầu tiên

## 1. Mục tiêu

Trong bài này, chúng ta tạo một ứng dụng Spring Shell nhỏ có command `hello`. Khi người dùng gọi command, ứng dụng trả về lời chào và có thể nhận tên qua option `--name`.

Sau khi hoàn thành, bạn sẽ biết cách:

- Tạo project Spring Boot có Spring Shell.
- Khai báo một command trong Spring-managed bean bằng annotation `@Command`.
- Nhận option bằng `@Option` và đặt giá trị mặc định.
- Khởi động shell, gọi command, xem trợ giúp và thoát khỏi phiên tương tác.
- Chạy command ở chế độ non-interactive khi cần gọi từ script.

Các ví dụ dùng API annotation của Spring Shell 4.x. Phiên bản này dùng `@Command`, `@Option` và `@Argument`; các annotation cũ `@ShellComponent`, `@ShellMethod` và `@ShellOption` thuộc mô hình trước đây và không còn được dùng trong 4.x.

## 2. Tạo project Spring Shell

Cách nhanh nhất là tạo một project Spring Boot từ [Spring Initializr](https://start.spring.io/), chọn Java, Maven hoặc Gradle, chọn phiên bản Spring Boot tương thích và thêm dependency **Spring Shell**. Initializr sẽ sinh cấu hình build và lớp khởi động cho ứng dụng.

Nếu project đã có sẵn, có thể thêm starter Spring Shell vào Maven:

~~~xml
<dependency>
    <groupId>org.springframework.shell</groupId>
    <artifactId>spring-shell-starter</artifactId>
    <version>4.0.3</version>
</dependency>
~~~

`spring-shell-starter` cung cấp các module cơ bản của Spring Shell và kéo theo `spring-boot-starter`. Nếu project sử dụng dependency management hoặc BOM của Spring Shell, hãy khai báo phiên bản tại BOM và bỏ phần `<version>` trong dependency để các module được quản lý đồng bộ.

Ví dụ này dùng Spring Shell 4.0.3 để minh họa API. Khi tạo project mới, hãy kiểm tra ma trận tương thích của phiên bản Spring Shell và Spring Boot được chọn; không ghép tùy ý các phiên bản khác major.

Một cấu trúc package đơn giản có thể như sau:

~~~text
src/main/java
└── com/example/greetings
    ├── GreetingApplication.java
    └── GreetingCommands.java
~~~

Đặt lớp command trong cùng package hoặc package con của lớp `@SpringBootApplication` để component scanning có thể tìm thấy bean.

## 3. Tạo lớp khởi động ứng dụng

Tạo lớp `GreetingApplication`:

~~~java
package com.example.greetings;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class GreetingApplication {

    public static void main(String[] args) {
        SpringApplication.run(GreetingApplication.class, args);
    }
}
~~~

`@SpringBootApplication` bật cấu hình tự động và component scanning cho package hiện tại cùng các package con. `SpringApplication.run(...)` tạo Spring application context, khởi tạo các bean và kích hoạt cơ chế chạy shell do starter cấu hình.

Trong ứng dụng Spring Boot với Spring Shell 4.x, command được khám phá tự động. Bạn không cần thêm `@EnableCommand` cho ví dụ này. Annotation đó được dùng khi tự cấu hình ứng dụng Spring không sử dụng Spring Boot.

## 4. Viết command `hello`

Tạo lớp `GreetingCommands` trong cùng package:

~~~java
package com.example.greetings;

import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class GreetingCommands {

    @Command(
            name = "hello",
            description = "Gửi lời chào đến một người",
            group = "Greetings",
            help = "Hiển thị lời chào. Có thể truyền tên bằng --name hoặc -n.")
    public String sayHello(
            @Option(
                    shortName = 'n',
                    longName = "name",
                    description = "Tên người được chào",
                    defaultValue = "World") String name) {
        return "Hello " + name + "!";
    }
}
~~~

Phương thức `sayHello` được Spring Shell đăng ký thành command nhờ annotation `@Command`. Các thuộc tính chính:

| Khai báo | Ý nghĩa |
|---|---|
| `@Component` | Đăng ký lớp `GreetingCommands` thành Spring bean để Spring Shell có thể khám phá phương thức command. |
| `name = "hello"` | Tên mà người dùng nhập trong shell. |
| `description` | Mô tả ngắn hiển thị trong danh sách trợ giúp. |
| `group = "Greetings"` | Nhóm command trong phần trợ giúp. |
| `help` | Hướng dẫn chi tiết hơn cho command. |
| `@Option` | Khai báo dữ liệu có tên mà người dùng có thể truyền vào. |
| `shortName = 'n'` | Bí danh ngắn của option, được gọi bằng `-n`. |
| `longName = "name"` | Tên đầy đủ của option, được gọi bằng `--name`. |
| `defaultValue = "World"` | Giá trị được dùng khi người gọi bỏ qua option. |

Phương thức trả về `String`. Spring Shell sẽ đưa giá trị trả về vào output của shell. Với command đơn giản, cách này giúp tập trung vào kết quả cần hiển thị mà không phải tự quản lý writer. Khi cần điều khiển output chi tiết hơn, có thể nhận `CommandContext` và sử dụng `outputWriter()`.

## 5. Khởi động và gọi command trong shell tương tác

Chạy ứng dụng từ thư mục project bằng Maven Wrapper trên Windows:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Trên macOS hoặc Linux:

~~~bash
./mvnw spring-boot:run
~~~

Khi ứng dụng khởi động xong, Spring Shell mở phiên tương tác và hiển thị dấu nhắc lệnh. Tùy terminal, dấu nhắc có thể có tên ứng dụng hoặc dạng `shell:>`.

Thử các lệnh sau:

~~~text
shell:>help
~~~

Lệnh `help` hiển thị danh sách command có sẵn. Trong đó, nhóm `Greetings` sẽ có command `hello` cùng mô tả ngắn đã khai báo.

Gọi command không truyền tên:

~~~text
shell:>hello
Hello World!
~~~

Kết quả dùng giá trị mặc định `World` vì option `--name` chưa được cung cấp.

Truyền tên bằng option đầy đủ:

~~~text
shell:>hello --name=Lan
Hello Lan!
~~~

Hoặc dùng tên ngắn:

~~~text
shell:>hello -n=Minh
Hello Minh!
~~~

Bạn cũng có thể yêu cầu trợ giúp riêng cho command:

~~~text
shell:>help hello
~~~

Phần trợ giúp cho biết mô tả, cú pháp và option mà command hỗ trợ. Đây là lý do nên đặt `description` và `help` có nội dung rõ ràng ngay từ khi khai báo command.

Khi muốn kết thúc phiên tương tác, nhập `exit` hoặc `quit` nếu các command built-in này được bật trong cấu hình mặc định của ứng dụng.

## 6. Chạy command một lần từ script

Shell tương tác phù hợp khi người dùng muốn nhập nhiều lệnh liên tiếp. Với script hoặc pipeline, thường cần gọi một command, nhận kết quả rồi kết thúc tiến trình. Spring Shell 4.x mặc định chạy ở chế độ interactive; có thể chuyển sang chế độ non-interactive bằng cấu hình:

~~~properties
spring.shell.interactive.enabled=false
~~~

Đặt thuộc tính trên trong `src/main/resources/application.properties`, sau đó đóng gói ứng dụng:

~~~powershell
.\mvnw.cmd clean package
~~~

Chạy command bằng cách truyền tên và option sau tên file JAR:

~~~powershell
java -jar target/greetings-0.0.1-SNAPSHOT.jar hello --name=Lan
~~~

Ứng dụng thực hiện command `hello`, in lời chào rồi kết thúc. Tên file JAR thực tế phụ thuộc vào `artifactId` và `version` trong project của bạn; hãy thay `greetings-0.0.1-SNAPSHOT.jar` bằng tên file được tạo trong thư mục `target`.

Nếu muốn quay lại phiên shell tương tác, bật lại thuộc tính:

~~~properties
spring.shell.interactive.enabled=true
~~~

Chỉ nên chọn một chế độ chạy phù hợp với cách sử dụng của ứng dụng. Phiên tương tác phục vụ người dùng làm việc trực tiếp; chế độ non-interactive phù hợp với lệnh được gọi từ script, CI hoặc một tiến trình khác.

## 7. Theo dõi luồng xử lý của command

Khi người dùng nhập `hello --name=Lan`, có thể hình dung các bước chính như sau:

~~~mermaid
flowchart TD
    A[Người dùng nhập hello --name=Lan] --> B[Shell nhận dòng lệnh]
    B --> C[Phân tích tên command và option]
    C --> D[Tra cứu command hello]
    D --> E[Chuyển giá trị Lan vào tham số name]
    E --> F[Thực thi sayHello]
    F --> G[Trả về Hello Lan!]
    G --> H[Shell hiển thị kết quả]
~~~

Spring Shell xử lý việc nhận dòng lệnh, tìm command và ánh xạ option vào tham số phương thức. Mã ứng dụng chỉ cần tập trung vào phần tạo lời chào. Khi option không được truyền, giá trị mặc định đã khai báo được đưa vào tham số `name`.

## 8. Những lỗi thường gặp

**Command không xuất hiện trong `help`:** kiểm tra lớp command có được đánh dấu `@Component` hoặc một stereotype Spring phù hợp không; kiểm tra lớp có nằm trong phạm vi component scanning của `@SpringBootApplication` không. Nếu package command nằm ngoài cây package của lớp khởi động, hãy điều chỉnh package hoặc cấu hình scan phù hợp.

**Không tìm thấy annotation:** xác nhận dependency là Spring Shell 4.x và import đúng package `org.springframework.shell.core.command.annotation`. Không dùng import `org.springframework.shell.standard.ShellMethod` hay `ShellComponent` của mô hình cũ.

**Tên option không khớp:** giá trị trong `longName` được gọi bằng hai dấu gạch ngang, ví dụ `--name`; giá trị trong `shortName` được gọi bằng một dấu gạch ngang, ví dụ `-n`.

**Không thấy output dù command đã chạy:** với phương thức trả về `String`, kiểm tra phương thức có trả về nội dung mong muốn không. Nếu command dùng `CommandContext`, hãy ghi qua `commandContext.outputWriter()` và flush writer khi cần.

**Ứng dụng ở lại terminal chờ nhập lệnh:** đây là hành vi bình thường khi interactive mode được bật. Nếu command cần chạy một lần từ script, hãy cấu hình `spring.shell.interactive.enabled=false` và truyền command qua tham số khởi chạy.

**Tác vụ kiểm thử bị treo:** khi kiểm thử ứng dụng Spring Shell bằng cách khởi tạo toàn bộ Spring Boot context, runner tương tác có thể chờ đầu vào terminal. Với kiểm thử non-interactive, cấu hình `spring.shell.interactive.enabled=false` và truyền command cần kiểm tra qua tham số test; với kiểm thử command riêng, ưu tiên các tiện ích kiểm thử của Spring Shell.

## 9. Bài tập thực hành

1. Đổi giá trị mặc định của `name` từ `World` thành tên của bạn. Gọi `hello` mà không truyền option và quan sát kết quả.
2. Thay đổi `description` và `help`, sau đó chạy `help` và `help hello` để kiểm tra nội dung trợ giúp.
3. Thêm một command `goodbye` trả về lời tạm biệt và đặt nó trong nhóm `Greetings`.
4. Chạy `hello --name=Lan` ở chế độ interactive, sau đó chuyển sang non-interactive và gọi cùng command từ terminal.
5. Thử bỏ `@Component` khỏi lớp command để quan sát command biến mất khỏi danh sách trợ giúp; khôi phục annotation sau khi hoàn thành.

## Kết luận

Một command Spring Shell 4.x đầu tiên có thể được tạo bằng cách đặt `@Command` trên một phương thức trong Spring bean. `@Option` ánh xạ giá trị người dùng nhập vào tham số Java, còn giá trị trả về của phương thức được hiển thị trong shell. Khi chạy với Spring Boot, starter khởi tạo shell và tự khám phá command. Từ ví dụ `hello`, bạn đã có nền tảng để bổ sung đối số, validation, trợ giúp, completion và các thao tác nghiệp vụ trong những bài tiếp theo.

## Tài liệu tham khảo

- [Spring Shell 4.x – Getting Started](https://docs.spring.io/spring-shell/reference/getting-started.html)
- [Spring Shell 4.x – Command Registration](https://docs.spring.io/spring-shell/reference/commands/registration.html)
- [Spring Shell 4.x – Command Syntax](https://docs.spring.io/spring-shell/reference/commands/syntax.html)
- [Spring Shell 4.x – Building and Starters](https://docs.spring.io/spring-shell/reference/building.html)
- [Spring Shell – v4 migration guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide)
