# Thay đổi của lệnh completion tích hợp khi chuyển sang 4.x

Khi nâng Spring Shell từ 3.x lên 4.x, lệnh tích hợp `completion` bị loại bỏ. Trong Spring Shell 3.1.3, người dùng có thể chạy `completion bash` để tạo script hỗ trợ hoàn thành lệnh ở Bash. Từ Spring Shell 4, framework không còn cung cấp lệnh tạo script này; việc cấu hình hoàn thành cho Bash, Zsh hoặc shell hệ điều hành khác do ứng dụng và người triển khai tự quản lý.

Điều này không có nghĩa Spring Shell 4 mất hoàn thành bằng phím Tab trong phiên shell tương tác. Hai chức năng cần được phân biệt:

- **Hoàn thành trong Spring Shell:** người dùng nhấn Tab tại prompt đang chạy để gợi ý command, option và giá trị. Chức năng này vẫn có trong JLine-based shell.
- **Hoàn thành ở shell hệ điều hành:** Bash hoặc Zsh gợi ý tên executable, command và option ngay tại prompt của hệ điều hành trước khi ứng dụng Spring Shell chạy. Lệnh tích hợp `completion` của 3.x từng hỗ trợ tạo script cho mục đích này; lệnh đó đã bị xóa trong 4.x.

## 1. Lệnh completion trong Spring Shell 3.x

Spring Shell 3.1.3 liệt kê `completion bash` trong nhóm Built-In Commands. Mô tả của lệnh là tạo script hoàn thành cho Bash. Phần tài liệu command-line completion cũng nêu Bash là shell hệ điều hành được hỗ trợ trong phiên bản này.

Khi chạy ứng dụng Spring Shell 3.1.x, có thể xem trợ giúp:

```text
shell:>help
AVAILABLE COMMANDS
Built-In Commands
    help: Display help about available commands
    completion bash: Generate bash completion script
    version: Show version info
    ...
```

Lệnh `completion bash` xuất nội dung script để Bash sử dụng. Có thể lưu kết quả vào file:

```bash
java -jar inventory-shell.jar completion bash > inventory-shell-completion.bash
```

Sau đó nạp script trong phiên Bash:

```bash
source ./inventory-shell-completion.bash
```

Hoặc thêm đường dẫn `source` vào `~/.bashrc` để Bash nạp script mỗi lần mở terminal. Cách cài đặt cụ thể phụ thuộc nơi ứng dụng và file completion được phân phối.

Lệnh tích hợp này phục vụ completion của shell hệ điều hành. Nó không phải cơ chế gợi ý Tab bên trong REPL. Spring Shell 3.x còn có completion tương tác thông qua JLine và các resolver riêng.

## 2. Điều gì thay đổi trong Spring Shell 4.x?

Migration Guide của Spring Shell 4 nêu rõ mục **Removal of the completion command**: command `completion` đã bị xóa; việc cấu hình completion được giao cho người dùng theo shell họ chọn, chẳng hạn Bash hoặc Zsh.

Vì vậy, khi chạy ứng dụng 4.x, không còn lệnh tích hợp tương đương:

```text
shell:>completion bash
```

Nếu script cài đặt hoặc tài liệu triển khai vẫn gọi lệnh này, nó sẽ thất bại vì command không còn được đăng ký. Không có command thay thế trực tiếp trong Spring Shell 4 để tự sinh script cho mọi shell hệ điều hành.

| Nhu cầu | Spring Shell 3.1.x | Spring Shell 4.x |
|---|---|---|
| Gợi ý command bằng Tab trong REPL | Có, với JLine-based shell | Có, với JLine-based shell |
| Gợi ý option và giá trị trong REPL | Có, dùng resolver/`ValueProvider` hoặc cấu hình builder | Có, dùng `CompletionProvider` ở cấp command |
| Tạo script Bash bằng command tích hợp | `completion bash` | Đã loại bỏ |
| Cài completion cho Bash/Zsh ở cấp hệ điều hành | Dùng script được tạo bởi lệnh tích hợp (Bash theo tài liệu 3.1.3) | Tự cung cấp và cài script theo shell mục tiêu |
| Provider tích hợp cho enum và file | `EnumValueProvider`, `FileValueProvider` trong API cũ | `EnumCompletionProvider`, `FileNameCompletionProvider` |

## 3. Không nhầm lệnh completion với Tab completion

Đây là điểm dễ gây nhầm lẫn nhất khi đọc migration guide. Spring Shell 4 loại bỏ command tạo script cho shell hệ điều hành, còn cơ chế gợi ý tương tác vẫn được duy trì.

| Loại completion | Cách hoạt động |
|---|---|
| **Hoàn thành trong REPL** | Người dùng đã khởi động ứng dụng và đang ở prompt `shell:>`. JLine đọc nội dung đang nhập, hỏi completion provider và hiển thị gợi ý khi nhấn Tab. |
| **Hoàn thành ở Bash/Zsh** | Người dùng đang ở prompt của hệ điều hành. Bash/Zsh chạy hàm completion đã cài để gợi ý tên executable, command và option trước khi gọi ứng dụng. |

Ví dụ, khi đang ở Spring Shell REPL:

```text
shell:>stock show --warehouse <nhấn Tab>
HN    HCM    DN
```

Đây là completion tương tác của Spring Shell/JLine. Trong khi đó, ở Bash:

```bash
$ inventory-shell stock <nhấn Tab>
show  adjust  import
```

Đây là completion do Bash script cung cấp. Hai cơ chế có thể gợi ý cùng một tập lệnh nhưng được triển khai và kích hoạt ở hai nơi khác nhau.

## 4. Hoàn thành tương tác trong Spring Shell 4 vẫn hoạt động

Tài liệu Spring Shell 4.0.4 xác nhận completion có sẵn trong JLine-based shell và được kích hoạt bằng phím Tab. Mặc định, shell gợi ý các command và option dựa trên phần văn bản đang nhập. Ứng dụng có thể tùy chỉnh bằng giao diện `CompletionProvider`.

Một điểm thay đổi quan trọng là Spring Shell 3 tổ chức completion giá trị theo từng option. Với annotation legacy, mỗi option có thể dùng `ValueProvider`; với `CommandRegistration`, resolver có thể được gắn vào từng `OptionSpec`. Cách tổ chức này khó cung cấp gợi ý phụ thuộc lẫn nhau giữa nhiều option.

Trong Spring Shell 4, completion được tập trung ở cấp command. Một `CompletionProvider` nhận `CompletionContext`, trong đó có thể xem command, option đang được hoàn thành và các từ đã nhập. Nhờ đó, một provider có thể đưa ra gợi ý dựa trên nhiều option hoặc trạng thái của cùng command.

### 4.1. Khai báo CompletionProvider cho command

Ví dụ command tra cứu tồn kho có hai option `--sku` và `--warehouse`. Danh sách kho được gợi ý cố định; mã SKU được truy vấn từ repository theo phần tiền tố người dùng đang nhập.

```java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.shell.core.command.CommandOption;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.shell.core.command.completion.CompletionContext;
import org.springframework.shell.core.command.completion.CompletionProposal;
import org.springframework.shell.core.command.completion.CompletionProvider;
import org.springframework.stereotype.Component;

@Component
public class StockCommands {

    @Command(
        name = "stock show",
        description = "Tra cứu tồn kho.",
        completionProvider = "stockShowCompletionProvider"
    )
    public String show(
            @Option(longName = "sku") String sku,
            @Option(longName = "warehouse") String warehouse) {
        return "SKU=" + sku + ", warehouse=" + warehouse;
    }

    @Bean
    CompletionProvider stockShowCompletionProvider(ProductRepository products) {
        return context -> {
            CommandOption option = context.getCommandOption();
            if (option == null) {
                return List.of();
            }

            if ("warehouse".equals(option.longName())) {
                return List.of(
                        new CompletionProposal("HN"),
                        new CompletionProposal("HCM"),
                        new CompletionProposal("DN"));
            }

            if ("sku".equals(option.longName())) {
                String prefix = context.currentWordUpToCursor();
                return products.findSkuStartingWith(prefix == null ? "" : prefix).stream()
                        .map(CompletionProposal::new)
                        .toList();
            }

            return List.of();
        };
    }
}
```

Tên bean `stockShowCompletionProvider` được tham chiếu trong thuộc tính `completionProvider` của `@Command`. Provider kiểm tra option hiện tại thông qua `CompletionContext.getCommandOption()` rồi tạo danh sách `CompletionProposal` tương ứng.

Ví dụ trên minh họa cấu trúc API; `ProductRepository.findSkuStartingWith(...)` là phương thức ứng dụng cần tự triển khai. Completion provider nên truy vấn nhanh, giới hạn số kết quả và tránh thao tác ghi dữ liệu vì nó được gọi trong lúc người dùng đang nhập.

### 4.2. Provider tích hợp và provider kết hợp

Spring Shell 4 cung cấp sẵn một số provider:

| Provider | Chức năng |
|---|---|
| `EnumCompletionProvider` | Gợi ý các hằng của enum |
| `FileNameCompletionProvider` | Gợi ý tên file và thư mục từ thư mục làm việc |
| `CompositeCompletionProvider` | Kết hợp nhiều provider thành một provider |
| `DefaultCompletionProvider` | Gợi ý mặc định cho option và giá trị enum theo metadata command |

Ví dụ kết hợp gợi ý định dạng báo cáo và tên file:

```java
@Bean
CompletionProvider reportCompletionProvider() {
    return new CompositeCompletionProvider(
            new EnumCompletionProvider(ReportFormat.class, "--format"),
            new FileNameCompletionProvider());
}
```

Provider này có thể được gắn vào `@Command(completionProvider = "reportCompletionProvider")`. Với cách đăng ký command bằng chương trình, có thể đặt provider bằng API `Command.Builder.completionProvider(...)`.

## 5. Những API completion 3.x cần rà soát khi nâng cấp

Ngoài command tích hợp bị xóa, Spring Shell 4 còn thay đổi API completion để thống nhất cách cấu hình ở cấp command.

| API trong 3.x | Tình trạng trong 4.x | Hướng chuyển đổi |
|---|---|---|
| Built-in command `completion bash` | Bị loại bỏ | Tự quản lý script completion cho Bash/Zsh hoặc shell mục tiêu |
| `ValueProvider` gắn với `@ShellOption` | Mô hình legacy bị loại bỏ cùng legacy annotation | Dùng `CompletionProvider` ở cấp `@Command` |
| `@OptionValues` | Bị loại bỏ | Chuyển logic gợi ý sang `CompletionProvider` |
| `EnumValueProvider` | Đổi tên thành `EnumCompletionProvider` | Cập nhật import và cấu hình provider |
| `FileValueProvider` | Đổi tên thành `FileNameCompletionProvider` | Cập nhật import và cấu hình provider |
| Completion resolver theo từng option | Thay bằng completion cấp command | Đọc option hiện tại và các từ đã nhập từ `CompletionContext` |

Nếu ứng dụng đang dùng legacy `@ShellMethod`/`@ShellOption`, cần chuyển command sang `@Command`/`@Option` trước hoặc trong quá trình nâng cấp vì legacy annotation đã bị loại bỏ trong 4.x. Không chỉ đổi tên `ValueProvider` rồi giữ nguyên cấu trúc cũ; cần chuyển điểm đăng ký completion sang command-level provider.

## 6. Tạo completion script riêng cho Bash

Vì Spring Shell 4 không còn tạo script bằng command `completion`, ứng dụng cần phân phối file Bash completion của riêng mình. Script này thuộc Bash và được nạp bởi Bash; Spring Shell không sinh hoặc tự cài nó.

Trước tiên, nên cung cấp một executable wrapper ổn định, ví dụ `inventory-shell`, để người dùng gọi ứng dụng:

```bash
#!/usr/bin/env bash
exec java -jar /opt/inventory/inventory-shell.jar "$@"
```

Đặt wrapper trong thư mục nằm trên `PATH`, sau đó tạo file `inventory-shell-completion.bash`:

```bash
_inventory_shell_complete() {
    local cur prev candidates
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"

    case "$prev" in
        --warehouse)
            candidates="HN HCM DN"
            ;;
        --format)
            candidates="csv json"
            ;;
        *)
            case "${COMP_WORDS[1]}" in
                stock)
                    candidates="show adjust import --sku --warehouse --quantity"
                    ;;
                report)
                    candidates="daily export --format"
                    ;;
                *)
                    candidates="help stock report version"
                    ;;
            esac
            ;;
    esac

    COMPREPLY=( $(compgen -W "$candidates" -- "$cur") )
}

complete -F _inventory_shell_complete inventory-shell
```

Nội dung trong script là danh sách ví dụ, cần điều chỉnh theo command, option và giá trị thực tế của ứng dụng. Với dữ liệu động như mã sản phẩm, có thể bổ sung nhánh gọi một command riêng ở chế độ non-interactive để lấy danh sách gợi ý; cần giới hạn thời gian chạy để thao tác Tab không bị chậm.

Nạp file trong Bash:

```bash
source /opt/inventory/inventory-shell-completion.bash
```

Để tự động nạp mỗi lần mở terminal, thêm dòng `source` vào `~/.bashrc` hoặc cài file vào thư mục completion của bản phân phối Linux đang dùng. Sau đó mở phiên Bash mới và thử:

```bash
inventory-shell stock <TAB>
inventory-shell stock show --warehouse <TAB>
```

Đây là ví dụ completion ở mức tên command và option. Một script hoàn chỉnh nên xét vị trí con trỏ, toàn bộ token đã nhập, dấu nháy, alias và giá trị hiện có của option để không đưa ra gợi ý sai ngữ cảnh.

## 7. Tích hợp với Zsh hoặc shell khác

Migration Guide không áp đặt một shell duy nhất; ứng dụng tự chọn cách phân phối completion theo môi trường người dùng. Với Zsh, viết function completion theo định dạng Zsh, khai báo command bằng `#compdef inventory-shell`, đặt file trong một thư mục thuộc `$fpath` và chạy `compinit` để nạp.

Ví dụ khung đơn giản:

```zsh
#compdef inventory-shell

_inventory_shell() {
  _arguments \
    '1:command:(help stock report version)' \
    '2:subcommand:(show adjust import daily export)' \
    '*:option:(--sku --warehouse --quantity --format)'
}

_inventory_shell "$@"
```

Đây là khung minh họa; nên phân nhánh theo command và subcommand thực tế để không gợi ý `show` cho `report` hoặc ngược lại. Cú pháp completion của Fish, PowerShell và các shell khác cũng có cơ chế riêng, vì vậy không thể dùng nguyên file Bash/Zsh cho chúng.

## 8. Spring Shell 4 cần JLine để có Tab completion trong REPL

Một thay đổi liên quan dễ bị bỏ sót khi nâng cấp là `spring-shell-core` không còn phụ thuộc JLine. Spring Shell 4 có `SystemShellRunner` dựa trên `java.io.Console`; runner này cung cấp chức năng terminal cơ bản nhưng không có command history, Tab completion hoặc định dạng văn bản phong phú.

Nếu cần tiếp tục trải nghiệm Tab completion bên trong Spring Shell REPL, ứng dụng phải dùng JLine-based shell:

- Thêm module `spring-shell-jline` khi tự cấu hình Spring Shell core.
- Hoặc dùng Spring Boot starter phù hợp, vì starter cấu hình JLine-based runner cho ứng dụng Boot.
- Nếu dùng cấu hình Java thuần, đăng ký `JLineShellRunner` theo tài liệu 4.x thay vì chỉ dùng `SystemShellRunner` mặc định.

Điểm này độc lập với việc command `completion` bị xóa. Thêm JLine giúp Tab completion trong REPL; nó không khôi phục lệnh `completion bash` và không tự cài script cho Bash/Zsh.

## 9. Quy trình nâng cấp completion từ 3.x lên 4.x

1. **Kiểm kê nơi đang dùng completion.** Tìm `completion bash`, `ValueProvider`, `@OptionValues`, `EnumValueProvider`, `FileValueProvider` và các script cài đặt trong README hoặc CI.
2. **Phân loại nhu cầu.** Xác định gợi ý nào phục vụ Tab trong REPL, gợi ý nào phục vụ Bash/Zsh ở prompt hệ điều hành.
3. **Chuyển completion trong REPL.** Dùng `CompletionProvider` ở cấp `@Command`, hoặc `Command.Builder.completionProvider(...)` với command đăng ký bằng chương trình.
4. **Cập nhật provider tích hợp.** Đổi `EnumValueProvider` thành `EnumCompletionProvider`, `FileValueProvider` thành `FileNameCompletionProvider`; chuyển `@OptionValues` sang logic provider.
5. **Tạo script cho shell hệ điều hành.** Viết và phân phối Bash/Zsh completion script riêng, hoặc cung cấp hướng dẫn cài đặt theo shell của người dùng.
6. **Bảo đảm runner có JLine.** Nếu người dùng cần Tab trong REPL, thêm `spring-shell-jline` hoặc starter cấu hình JLine.
7. **Kiểm thử cả hai môi trường.** Kiểm tra Tab trong REPL và completion tại prompt hệ điều hành; đây là hai bài kiểm thử khác nhau.
8. **Xóa hướng dẫn cũ.** Cập nhật tài liệu, script cài đặt và pipeline còn gọi `completion bash` sau khi chuyển lên 4.x.

## 10. Checklist kiểm thử sau migration

| Trường hợp | Kết quả mong đợi |
|---|---|
| Gõ command và nhấn Tab trong JLine REPL | Gợi ý command và option vẫn xuất hiện |
| Gõ giá trị enum sau option | `EnumCompletionProvider` đưa ra các giá trị hợp lệ |
| Gõ đường dẫn sau option file | `FileNameCompletionProvider` gợi ý file/thư mục |
| Gợi ý phụ thuộc option đã nhập | `CompletionProvider` đọc context và trả gợi ý đúng |
| Chạy `completion bash` trên 4.x | Không còn command này; tài liệu triển khai không được yêu cầu chạy nó |
| Nạp script Bash riêng | Bash hoàn thành command/option theo script đã cài |
| Dùng `SystemShellRunner` không có JLine | Không kỳ vọng có Tab completion |
| Dùng JLine runner | Tab completion tương tác hoạt động |
| Dùng Zsh | Script Zsh được nạp qua `$fpath`/`compinit` và hoạt động theo định nghĩa |

Nên kiểm thử trong terminal thật của shell mục tiêu. Test Java cho `CompletionProvider` có thể xác nhận danh sách proposal, nhưng không chứng minh Bash/Zsh đã nạp đúng file hoặc xử lý đúng cú pháp completion.

## 11. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `completion bash` báo không tìm thấy command | Đang chạy Spring Shell 4.x | Thay bằng script Bash do ứng dụng quản lý |
| Tab không hoạt động trong REPL 4.x | Đang dùng `SystemShellRunner` không có JLine | Thêm `spring-shell-jline` hoặc dùng starter cấu hình JLine |
| Provider không được gọi | Tên bean trong `completionProvider` không khớp hoặc command chưa đăng ký provider | Kiểm tra bean name và metadata `@Command` |
| Provider chỉ gợi ý theo một option, không xét option khác | Logic cũ được chuyển nguyên xi từ `ValueProvider` | Dùng `CompletionContext` ở cấp command để xét option và token đã nhập |
| Import `EnumValueProvider` không còn | API được đổi tên | Dùng `EnumCompletionProvider` |
| Import `FileValueProvider` không còn | API được đổi tên | Dùng `FileNameCompletionProvider` |
| `@OptionValues` không biên dịch | Annotation đã bị loại bỏ | Chuyển sang `CompletionProvider` |
| Bash completion hoạt động nhưng Zsh không hoạt động | Script Bash không tương thích Zsh | Viết và cài script theo cú pháp Zsh |
| Completion chậm | Provider truy vấn mạng hoặc dữ liệu lớn mỗi lần nhấn Tab | Cache dữ liệu phù hợp, giới hạn kết quả và giảm chi phí truy vấn |

## 12. Tổng kết

Thay đổi lớn khi chuyển sang Spring Shell 4 là command tích hợp `completion` dùng để tạo script cho shell hệ điều hành đã bị loại bỏ. Ứng dụng phải tự quản lý completion script theo Bash, Zsh hoặc shell mục tiêu. Trong Spring Shell 3.1.x, `completion bash` được liệt kê trong trợ giúp tích hợp và tài liệu mô tả khả năng tạo script Bash.

Completion bằng Tab trong REPL vẫn được hỗ trợ khi dùng JLine-based shell. Spring Shell 4 chuyển việc gợi ý giá trị sang `CompletionProvider` cấp command, hỗ trợ logic dựa trên nhiều option và thay thế các API cũ như `ValueProvider`/`@OptionValues`; các provider enum và file cũng được đổi tên. Khi nâng cấp, hãy kiểm tra riêng completion trong REPL, completion của shell hệ điều hành, runner JLine và script triển khai.

## Tài liệu tham khảo

- [Spring Shell 3.1.3 Reference Documentation](https://docs.spring.io/spring-shell/docs/3.1.3/docs/index.html) — mục 4.8.7 Built-In Commands: Completion và chương 6 Completion.
- [Spring Shell 3.1.x Completion API](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/standard/commands/Completion.html) — command `completion bash` và các phương thức tạo script.
- [Spring Shell 4.x Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide) — mục Removal of the completion command, Command completion và API changes.
- [Spring Shell 4.0.4 Command Completion](https://docs.spring.io/spring-shell/reference/commands/completion.html) — JLine Tab completion, CompletionProvider và các provider tích hợp.
- [CompletionProvider API 4.0.3](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/completion/CompletionProvider.html) — hợp đồng tạo completion proposals.
- [CompletionContext API 4.0.4](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/completion/CompletionContext.html) — ngữ cảnh command, option và nội dung đang nhập.
- [Spring Shell 4.x Shell Runner Migration](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide) — khác biệt giữa SystemShellRunner và JLineShellRunner.
