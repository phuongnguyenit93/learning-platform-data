# Bí danh lệnh và điều kiện hỗ trợ của API đang dùng

Bí danh (alias) cho phép người dùng gọi cùng một command bằng nhiều tên. Ví dụ, một thao tác tìm khách hàng có thể được gọi bằng `customer find`, `customer get` hoặc `cust find`. Các tên này cùng dẫn tới một xử lý, nên người dùng có thể dùng tên ngắn hơn hoặc tiếp tục dùng cú pháp cũ trong thời gian ứng dụng đổi tên lệnh.

Spring Shell có nhiều mô hình đăng ký command. Cách khai báo bí danh phụ thuộc API mà dự án đang dùng: annotation legacy `@ShellMethod`, annotation mới `@Command` hoặc đăng ký programmatic bằng `CommandRegistration`. Các API này có cú pháp và quy tắc ghép tên khác nhau; cần đối chiếu phiên bản dependency trước khi sao chép ví dụ.

Spring Shell hỗ trợ xây dựng CLI bằng khai báo command, xử lý đối số, validation, trợ giúp và tự hoàn thành. Bài này tập trung vào cách đặt bí danh cho command, cách phân biệt bí danh command với bí danh option và những điều kiện phiên bản cần kiểm tra để chọn đúng API.

Sau bài này, bạn có thể:

- Giải thích mục đích và cách thiết kế bí danh command.
- Khai báo nhiều tên gọi bằng `@ShellMethod(key = ...)` trong mô hình legacy.
- Khai báo alias bằng `@Command(alias = ...)` trong mô hình annotation mới của Spring Shell 3.x.
- Đăng ký alias bằng `CommandRegistration.Builder.withAlias()` trong mô hình programmatic 3.x.
- Nhận biết các khác biệt quan trọng giữa Spring Shell 2.x, 3.x và 4.x.
- Kiểm tra alias, tránh xung đột tên và duy trì tương thích khi đổi tên command.

## 1. Bí danh command là gì?

Một command có một hành vi chính nhưng có thể được gọi bằng nhiều tên. Ví dụ:

```text
customer find --id 42
customer get --id 42
cust find --id 42
```

Nếu ba cách gọi được khai báo làm bí danh của cùng command, Spring Shell chuyển chúng tới cùng target. Người dùng có thể chọn cách gõ phù hợp mà ứng dụng vẫn giữ một nơi triển khai nghiệp vụ.

Bí danh thường hữu ích trong ba tình huống:

1. **Tên rút gọn:** cung cấp tên ngắn cho lệnh thường dùng, chẳng hạn `cust list`.
2. **Tương thích ngược:** giữ tên cũ khi command được đổi tên, giúp script và thói quen của người dùng không bị gián đoạn ngay lập tức.
3. **Từ đồng nghĩa dễ nhớ:** hỗ trợ các cách diễn đạt quen thuộc như `show`, `get` hoặc `view` cho cùng một thao tác đọc dữ liệu.

Không nên tạo quá nhiều alias. Danh sách tên gọi quá dài làm giao diện khó học, khó tài liệu hóa và tăng khả năng xung đột với command khác.

### Phân biệt bí danh command và bí danh option

Hai loại bí danh này nằm ở hai cấp khác nhau:

| Loại | Ví dụ | Ý nghĩa |
|---|---|---|
| Bí danh command | `customer find` và `customer get` | Hai tên command gọi cùng một thao tác. |
| Bí danh option | `customer find -i 42` và `customer find --id 42` | Hai tên option truyền cùng một tham số. |

Với API legacy, option có thể khai báo nhiều tên bằng `@ShellOption(value = {"-i", "--id"})`. Cấu hình này không tạo bí danh cho command `customer find`; nó chỉ cho phép hai cách viết của tham số `id`.

Ngoài ra, bí danh command trong Spring Shell là một phần của command catalog. Nó khác alias được định nghĩa trong Bash, PowerShell hoặc file profile của hệ điều hành. Alias của hệ điều hành không tự động trở thành command của Spring Shell và có thể không tồn tại khi command chạy trong script hoặc môi trường khác.

## 2. Mô hình legacy: nhiều key trong `@ShellMethod`

Trong API legacy của Spring Shell 2.x và 3.x, lớp command được đánh dấu `@ShellComponent`, còn phương thức được đánh dấu `@ShellMethod`. Thuộc tính `key` nhận một hoặc nhiều tên command. Khi truyền nhiều key, mỗi key là một tên gọi riêng cho cùng phương thức.

```java
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.standard.ShellOption;

@ShellComponent
public class CustomerCommands {

    @ShellMethod(
            value = "Tìm khách hàng theo mã.",
            key = {"customer find", "customer get", "cust find"})
    public String find(
            @ShellOption(value = {"-i", "--id"}) long id) {
        return "Đang tìm khách hàng #" + id;
    }
}
```

Ba key trên là ba tên command hoàn chỉnh. Người dùng có thể gọi:

```text
customer find --id 42
customer get --id 42
cust find -i 42
```

Trong cả ba trường hợp, Spring Shell gọi phương thức `find()` và ánh xạ `id` như nhau. Tên trong `key` có thể gồm nhiều từ; dấu cách phân chia các thành phần của command.

### Quy tắc cần nhớ của `key`

- Nếu không khai báo `key`, Spring Shell suy ra tên từ tên phương thức, thường chuyển camelCase thành kebab-case.
- Nếu `key` có một giá trị, đó là tên command được chỉ định rõ.
- Nếu `key` có nhiều giá trị, từng giá trị là một tên gọi khác nhau của cùng phương thức.
- Các key là tên đầy đủ. Không có cơ chế tự động lấy một phần của key đầu tiên làm tiền tố cho các key còn lại.
- `@ShellMethod.value` vẫn là mô tả ngắn của command, không phải bí danh.

Mô hình này phù hợp với ứng dụng đang sử dụng `@ShellComponent` và `@ShellMethod`. Nếu dự án đã chuyển sang annotation mới hoặc đăng ký programmatic, hãy dùng cơ chế tương ứng thay vì trộn hai mô hình trong cùng một command.

## 3. Mô hình annotation mới trong Spring Shell 3.x: `@Command(alias = ...)`

Spring Shell bổ sung mô hình annotation mới từ dòng 3.1.x. Mô hình này dùng `@Command` thay cho cặp annotation legacy `@ShellComponent` và `@ShellMethod`. Trong Spring Shell 3.x, thuộc tính `command` xác định tên command, còn `alias` khai báo tên thay thế.

Ví dụ một command có nhiều alias:

```java
import org.springframework.shell.command.annotation.Command;

@Command
public class CustomerCommands {

    @Command(command = "customer find",
            alias = {"customer get", "cust find"},
            description = "Tìm khách hàng theo mã.")
    public String find() {
        return "Đang tìm khách hàng.";
    }
}
```

Trong ví dụ, `customer find` là tên chính; `customer get` và `cust find` là hai alias. Mỗi phần tử của mảng `alias` là một tên thay thế. Với alias nhiều từ, có thể viết toàn bộ tên trong một chuỗi như ví dụ trên.

### Dùng tiền tố ở cấp lớp

Trong Spring Shell 3.x, `@Command` có thể được đặt ở cấp lớp để chia sẻ tiền tố và cấu hình với các phương thức command bên trong. Alias ở cấp lớp được dùng làm tiền tố cho alias ở cấp phương thức:

```java
import org.springframework.shell.command.annotation.Command;

@Command(command = "customer", alias = "cust")
public class CustomerCommands {

    @Command(command = "find", alias = "get",
            description = "Tìm khách hàng theo mã.")
    public String find() {
        return "Đang tìm khách hàng.";
    }
}
```

Tên chính là `customer find`; alias được ghép thành `cust get`. Cấp lớp cung cấp phần tiền tố, còn cấp phương thức cung cấp phần lệnh con và alias tương ứng.

Có một quy tắc dễ bỏ sót: nếu chỉ khai báo alias ở cấp lớp nhưng phương thức không khai báo alias ở cấp phương thức, alias cấp lớp không tự tạo ra một tên thay thế cho mọi command. Alias cấp lớp đóng vai trò tiền tố khi alias cấp phương thức được khai báo. Hãy kiểm tra trường hợp này nếu `help` không hiển thị hoặc shell không nhận tên thay thế như mong đợi.

### Bật đăng ký command trong mô hình annotation mới

Trong Spring Shell 3.x, chỉ đặt `@Command` lên lớp và phương thức chưa đủ để đăng ký target. Cần bật việc phát hiện command bằng `@EnableCommand` hoặc `@CommandScan`:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.command.annotation.EnableCommand;

@Configuration
@EnableCommand(CustomerCommands.class)
public class ShellCommandConfiguration {
}
```

Hoặc dùng `@CommandScan` trên cấu hình ứng dụng để quét các command target trong phạm vi package được chọn. Đây là điều kiện đăng ký của mô hình annotation mới trong Spring Shell 3.x. Nếu quên bước này, command và alias có thể không xuất hiện trong command catalog dù annotation đã được viết đúng.

## 4. Mô hình programmatic trong Spring Shell 3.x: `withAlias()`

Khi đăng ký command bằng `CommandRegistration`, có thể tạo alias qua `withAlias()`. Mỗi lần gọi `withAlias()` mở một cấu hình alias; `command(...)` đặt tên alias và `and()` quay lại builder chính.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.command.CommandRegistration;

@Configuration
public class CustomerCommandConfiguration {

    @Bean
    CommandRegistration customerFindCommand() {
        return CommandRegistration.builder()
                .command("customer", "find")
                .description("Tìm khách hàng theo mã.")
                .withAlias()
                    .command("customer", "get")
                    .and()
                .withAlias()
                    .command("cust", "find")
                    .and()
                .withTarget()
                    .function(context -> "Đang tìm khách hàng.")
                    .and()
                .build();
    }
}
```

Command chính là `customer find`; hai alias là `customer get` và `cust find`. Mỗi khối `withAlias()` tạo một alias riêng. Trong `AliasSpec`, các phần tử truyền vào `command(String...)` được ghép thành một tên nhiều từ. Vì vậy, `.command("cust", "find")` tạo một alias `cust find`, không phải hai alias đơn lẻ `cust` và `find`.

Nếu cần ba alias, khai báo ba khối `withAlias()`. Cách viết tường minh này giúp người đọc nhận biết chính xác tên nào được tạo ra và tránh nhầm lẫn giữa danh sách token của một tên nhiều từ với danh sách các alias.

## 5. So sánh API và điều kiện hỗ trợ theo phiên bản

Không phải ví dụ alias nào cũng dùng được trong mọi phiên bản Spring Shell. Bảng sau giúp chọn đúng cách triển khai:

| API | Spring Shell 2.x | Spring Shell 3.x | Spring Shell 4.x |
|---|---|---|---|
| `@ShellMethod(key = {...})` | Có, là mô hình legacy | Có, nhưng thuộc mô hình legacy đã bị deprecated | Đã bị loại bỏ |
| `@Command(command = ..., alias = ...)` | Không có trong mô hình 2.x | Có từ dòng 3.1.x; hỗ trợ alias ở cấp lớp và phương thức | `@Command(name = ..., alias = ...)` chỉ còn ở cấp phương thức; dùng `@CommandGroup` cho tiền tố/nhóm |
| `CommandRegistration.withAlias()` | Không dùng API 3.x này | Có trong mô hình programmatic 3.x | Mô hình programmatic đã được thiết kế lại quanh `Command` và `CommandRegistry` |

Các khác biệt quan trọng:

- **Spring Shell 2.x:** nếu dùng annotation, khai báo nhiều key trong `@ShellMethod`. Không sao chép `@Command(alias = ...)` của mô hình 3.x vào dự án 2.x.
- **Spring Shell 3.x:** có cả API legacy và mô hình mới. `@ShellMethod` vẫn hoạt động trong các bản 3.x nhưng đã được đánh dấu legacy/deprecated; `@Command` và `CommandRegistration` là các lựa chọn mới hơn.
- **Spring Shell 4.x:** các annotation legacy như `@ShellComponent`, `@ShellMethod` và `@ShellOption` đã bị loại bỏ. Annotation mới dùng package `org.springframework.shell.core.command.annotation`; thuộc tính `command` đổi thành `name`, và `@Command` không còn đặt ở cấp lớp. Dùng `@CommandGroup` khi cần tiền tố và nhóm chung.
- **Programmatic 4.x:** API đăng ký command được thiết kế lại quanh `Command` và `CommandRegistry`; không giả định builder `CommandRegistration` của 3.x vẫn giữ nguyên.

Trước khi chọn ví dụ, hãy kiểm tra phiên bản `spring-shell` thực tế trong Maven hoặc Gradle, package import mà IDE resolve và tài liệu API tương ứng. Không chỉ dựa vào phiên bản Spring Boot vì một dự án có thể quản lý Spring Shell qua BOM hoặc dependency management riêng.

## 6. Chọn một mô hình nhất quán cho dự án

Nếu code hiện tại dùng `@ShellComponent` và `@ShellMethod`, cách thay đổi ít nhất là thêm alias vào mảng `key`. Nếu dự án đã sử dụng mô hình `@Command` mới của Spring Shell 3.x, khai báo `alias` ở đúng cấp lớp hoặc phương thức. Nếu command được tạo bằng `CommandRegistration`, dùng `withAlias()`.

Không nên định nghĩa cùng một command trong nhiều mô hình chỉ để có thêm alias. Việc trộn nhiều registration path có thể làm command catalog có tên trùng, khiến người bảo trì khó xác định target nào được gọi. Chọn một cơ chế làm nguồn đăng ký cho command đó và kiểm tra kết quả sau khi Spring khởi tạo.

Một quy ước đặt tên hữu ích:

1. Giữ một tên chính theo cấu trúc nhất quán, ví dụ `customer find`.
2. Chọn alias ngắn nhưng vẫn có nghĩa, ví dụ `cust find`.
3. Khi đổi tên, giữ alias cũ trong thời gian chuyển tiếp nếu cần tương thích script.
4. Ghi alias trong tài liệu CLI và ví dụ sử dụng.
5. Đặt lịch loại bỏ alias cũ khi người dùng và script đã chuyển sang tên mới.

## 7. Kiểm tra alias sau khi đăng ký

Sau khi khởi động ứng dụng, chạy `help` để xác nhận command chính đã được đăng ký. Trợ giúp chi tiết giúp kiểm tra cú pháp và mô tả. Tuy nhiên, không nên mặc định mọi template trợ giúp sẽ hiển thị toàn bộ alias theo cùng một định dạng; hãy gọi trực tiếp từng tên để xác nhận hành vi.

Ví dụ kiểm tra thủ công:

```text
help
help customer find
customer find --id 42
customer get --id 42
cust find --id 42
```

Với mô hình programmatic, có thể viết integration test để gọi từng tên qua test client hoặc test harness mà phiên bản Spring Shell đang dùng hỗ trợ. Mỗi tên phải dẫn tới cùng target và nhận tham số tương đương.

Các điểm cần kiểm tra:

- Command chính gọi đúng target.
- Từng alias gọi cùng target với command chính.
- Alias nhiều từ được nhập đúng thứ tự token.
- Option và alias option hoạt động giống nhau qua tất cả tên command.
- Không có alias trùng với command khác hoặc alias của command khác.
- Command được đăng ký đúng một lần, không có target trùng ngoài dự kiến.
- Script đang dùng tên cũ vẫn chạy trong giai đoạn tương thích.

## 8. Xử lý xung đột và đổi tên command

Alias cần duy nhất trong phạm vi command catalog. Nếu hai command cùng nhận một tên, việc phân giải có thể trở nên mơ hồ hoặc gây lỗi đăng ký tùy cơ chế và phiên bản. Đừng dựa vào thứ tự khởi tạo bean để quyết định target nào thắng.

Khi đổi `customer search` thành `customer find`, có thể triển khai theo các bước:

1. Đặt `customer find` làm tên chính.
2. Thêm `customer search` làm alias chuyển tiếp.
3. Cập nhật tài liệu và ví dụ để ưu tiên tên mới.
4. Ghi log hoặc thống kê nếu cần biết alias cũ còn được sử dụng hay không.
5. Thông báo thời điểm loại bỏ alias cũ.
6. Xóa alias sau khi các script và người dùng đã chuyển đổi.

Không đổi target hoặc ý nghĩa nghiệp vụ chỉ vì thêm alias. Bí danh là một cách gọi khác của cùng thao tác; nếu hai tên cần hành vi khác nhau, hãy khai báo hai command riêng và tách logic tương ứng.

## 9. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Alias trong `@ShellMethod` không chạy | Key chưa được khai báo trong mảng hoặc nhập sai tên nhiều từ | Kiểm tra toàn bộ giá trị `key` và gọi đúng chuỗi. |
| `@Command(alias = ...)` không được đăng ký | Chưa bật `@EnableCommand` hoặc `@CommandScan` trong Spring Shell 3.x | Bổ sung cơ chế đăng ký target của mô hình annotation mới. |
| Alias cấp lớp không hoạt động | Chỉ khai báo alias ở cấp lớp nhưng phương thức không có alias tương ứng | Khai báo alias ở cấp phương thức theo quy tắc ghép tiền tố. |
| `withAlias()` tạo tên khác mong đợi | Nhầm các phần tử trong `command(String...)` là nhiều alias riêng | Dùng một khối `withAlias()` cho mỗi alias và truyền các token của tên nhiều từ vào cùng khối. |
| Lỗi import sau khi nâng cấp lên 4.x | Package thay đổi và API legacy bị loại bỏ | Dùng annotation và package của Spring Shell 4.x; chuyển `command` sang `name`. |
| Command chạy nhầm target | Tên chính hoặc alias bị trùng giữa các registration | Tìm và loại bỏ tên trùng trong command catalog. |
| Alias chạy nhưng option không được nhận | Nhầm bí danh command với bí danh option hoặc cú pháp option không khớp | Kiểm tra riêng key/alias command và metadata của từng option. |

## 10. Bài tập thực hành

Tạo command quản lý khách hàng với tên chính `customer find`. Thực hiện bài tập theo API mà dự án đang sử dụng:

1. Thêm alias `customer get` và `cust find`.
2. Giữ option `--id` và bí danh `-i` cho mã khách hàng.
3. Gọi cả ba tên với cùng một mã và xác nhận chúng chạy cùng xử lý.
4. Kiểm tra `help` và trợ giúp chi tiết sau khi khởi động.
5. Thử khai báo một alias trùng với tên command khác và quan sát cách ứng dụng phát hiện xung đột; sau đó loại bỏ xung đột.
6. Đổi tên chính từ `customer find` sang `customer lookup`, giữ `customer find` làm alias tương thích.
7. Ghi lại API, package import và phiên bản Spring Shell của dự án để giải thích vì sao cú pháp alias đó được hỗ trợ.

Khi hoàn thành, bạn cần giải thích được bí danh command khác bí danh option ở điểm nào, mỗi API tạo alias ra sao và những thay đổi nào cần thực hiện khi nâng cấp phiên bản Spring Shell.

## Tài liệu tham khảo

- [Spring Shell 3.3 – Alias](https://docs.spring.io/spring-shell/reference/3.3/commands/alias.html): khai báo alias bằng `CommandRegistration` và `@Command`.
- [Spring Shell 3.3 – Legacy Annotation](https://docs.spring.io/spring-shell/reference/3.3/commands/registration/legacyannotation.html): nhiều key trong `@ShellMethod` và hành vi của API legacy.
- [Spring Shell 3.3 – Annotation Registration](https://docs.spring.io/spring-shell/reference/3.3/commands/registration/annotation.html): `@Command`, `@EnableCommand` và `@CommandScan`.
- [CommandRegistration.AliasSpec API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/command/CommandRegistration.AliasSpec.html): cấu hình alias trong mô hình programmatic 3.x.
- [Spring Shell 4 Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide): các thay đổi breaking khi chuyển từ 3.x lên 4.x.
