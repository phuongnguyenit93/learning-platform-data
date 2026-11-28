# Phân biệt chuỗi gốc với danh sách đối số đã qua shell hệ điều hành

Khi người dùng nhập một lệnh vào terminal, chương trình đích thường không nhận nguyên văn dòng ký tự mà người dùng đã gõ. Shell của hệ điều hành phân tích dòng lệnh trước, xử lý dấu nháy, biến môi trường, ký tự đặc biệt và tách thành các đối số. Java sau đó nhận một mảng `String[]` trong `main`. Vì vậy, **chuỗi gốc và danh sách đối số là hai biểu diễn khác nhau**.

Điều này quan trọng khi xây dựng CLI bằng Spring Shell. Một dòng nhập trong prompt Spring Shell được parser của Spring Shell xử lý trực tiếp như văn bản lệnh. Khi chạy ứng dụng từ Bash, PowerShell hoặc `cmd.exe`, các quy tắc của shell hệ điều hành đã tác động trước khi Spring Shell nhận được đối số. Bài viết làm rõ ranh giới này, cách quan sát dữ liệu thực tế và cách truyền giá trị có khoảng trắng hoặc ký tự đặc biệt an toàn hơn.

## 1. Hai biểu diễn cần phân biệt

Giả sử người dùng gõ:

```bash
java -jar catalog-cli.jar search --query "spring shell guide"
```

Có thể nhìn lệnh này theo hai cách:

- **Chuỗi lệnh gốc (raw command text):** toàn bộ văn bản người dùng nhập, bao gồm dấu nháy, khoảng trắng, ký tự escape và cú pháp riêng của shell.
- **Danh sách đối số (argument vector, thường gọi là `argv`):** danh sách các chuỗi mà tiến trình nhận được sau khi shell và trình khởi chạy xử lý lệnh.

Trong ví dụ trên, dấu nháy kép được dùng để giữ `spring shell guide` thành một đối số duy nhất. Dấu nháy chỉ có vai trò cú pháp; nó thường bị loại bỏ trước khi Java nhận giá trị.

| Biểu diễn | Giá trị minh họa |
|---|---|
| Văn bản người dùng gõ | `java -jar catalog-cli.jar search --query "spring shell guide"` |
| Đối số ứng dụng nhận | `args[0] = "search"` |
|  | `args[1] = "--query"` |
|  | `args[2] = "spring shell guide"` |

Mảng `args` giữ ranh giới giữa các đối số, nhưng không lưu lại cách người dùng đã viết dòng lệnh. Ứng dụng không biết người dùng đã dùng dấu nháy đơn, dấu nháy kép hay ký tự escape để tạo ra cùng một giá trị.

## 2. Đường đi của một lệnh từ terminal đến command method

Khi khởi chạy ứng dụng Java từ shell hệ điều hành, dữ liệu đi qua nhiều lớp:

```text
Người dùng nhập dòng lệnh
        |
        v
Bash / PowerShell / cmd.exe phân tích cú pháp
        |
        v
Expansion, quote handling, word splitting, escaping
        |
        v
Trình khởi chạy Java nhận đối số của chính nó
        |
        v
Java launcher tạo String[] cho main(String[] args)
        |
        v
Spring Boot nhận application arguments
        |
        v
Spring Shell runner nhận String[] args
        |
        v
Spring Shell parser phân tích command, option và argument
        |
        v
Command method được gọi với tham số đã bind
```

Các lớp không có cùng trách nhiệm:

1. **Shell hệ điều hành** xử lý cú pháp của Bash, PowerShell hoặc `cmd.exe`. Đây là nơi dấu nháy được dùng để nhóm từ, biến môi trường được thay thế hoặc wildcard được mở rộng.
2. **Java launcher** phân biệt tùy chọn JVM, class/JAR được chạy và đối số dành cho ứng dụng. Các đối số sau tên class hoặc sau `-jar jarfile` được chuyển đến `main`.
3. **Java application** chỉ nhận mảng chuỗi `String[] args`; nó không được cung cấp một bản sao phổ quát của dòng lệnh gốc mà người dùng đã nhập.
4. **Spring Shell** phân tích đầu vào theo cú pháp command của nó, rồi bind token vào `@Argument`, `@Option` hoặc `@Arguments`.

Ranh giới tiến trình cũng khác nhau giữa hệ điều hành. Trên hệ Unix-like, shell thường gọi `execve` với một mảng `argv` đã được tạo. Trên Windows, API `CreateProcess` nhận một chuỗi command line; chương trình được khởi chạy hoặc runtime của nó phải diễn giải chuỗi đó thành đối số. `CommandLineToArgvW` là một hàm phân tích phổ biến của Windows, nhưng không phải mọi chương trình native đều bắt buộc dùng cùng một parser. Java launcher tiếp tục chuyển dữ liệu khởi chạy thành `String[]` cho `main`.

Khi chạy command trong prompt tương tác của Spring Shell, đường đi khác ở bước đầu: Spring Shell đọc một dòng văn bản từ terminal và chuyển dòng đó cho command parser. Dấu nháy khi ấy thuộc cú pháp của Spring Shell, không phải cú pháp dùng để khởi chạy tiến trình Java.

## 3. Java `main(String[] args)` nhận dữ liệu gì?

Java launcher truyền các đối số dành cho ứng dụng vào mảng `String[]`. Với chế độ chạy JAR, các token sau `-jar` và tên JAR là đối số của ứng dụng:

```bash
java [JVM options] -jar catalog-cli.jar [application arguments...]
```

Ví dụ:

```bash
java -Xmx512m -Dapp.region=apac -jar catalog-cli.jar search --query "spring shell guide"
```

Trong đó:

- `-Xmx512m` là tùy chọn JVM.
- `-Dapp.region=apac` là Java System Property, cũng là tùy chọn JVM.
- `-jar catalog-cli.jar` chỉ định ứng dụng cần chạy.
- `search`, `--query` và giá trị tìm kiếm là application arguments được truyền cho `main`.

`args[0]` là đối số ứng dụng đầu tiên, không phải tên executable `java`, không phải `-jar` và cũng không phải tên file JAR.

### In từng đối số để quan sát ranh giới thực tế

Trong lúc phát triển, có thể tạm thời in nội dung và chỉ số của từng đối số:

```java
public class ArgumentProbe {

    public static void main(String[] args) {
        System.out.println("Argument count: " + args.length);

        for (int i = 0; i < args.length; i++) {
            System.out.printf("args[%d] = <%s>%n", i, args[i]);
        }
    }
}
```

Nếu chạy:

```bash
java ArgumentProbe search --query "spring shell guide"
```

Kết quả có dạng:

```text
Argument count: 3
args[0] = <search>
args[1] = <--query>
args[2] = <spring shell guide>
```

Các ký tự `<` và `>` trong kết quả chỉ là dấu phân cách do chương trình in ra. Chúng giúp nhìn thấy khoảng trắng ở đầu hoặc cuối một giá trị nếu có.

Không dùng `args.toString()` để xem nội dung mảng. Cách đó in ra định danh đối tượng mảng, không in từng phần tử. `Arrays.toString(args)` cũng hữu ích cho kiểm tra nhanh, nhưng vòng lặp có chỉ số rõ hơn khi cần phát hiện đối số rỗng hoặc khoảng trắng ở đầu/cuối.

### Spring Boot `ApplicationArguments` không khôi phục dòng lệnh gốc

Trong ứng dụng Spring Boot, `ApplicationArguments` là lớp tiện ích bao quanh application arguments. Nó cho phép đọc `getSourceArgs()`, tên option, giá trị option và các non-option argument. Đây là cách phân loại mảng đối số cho code khởi động; nó không lưu lại dấu nháy hoặc cú pháp gốc của shell hệ điều hành.

Ví dụ một `ApplicationRunner` có thể quan sát:

```java
import java.util.Arrays;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class ArgumentsReporter implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments arguments) {
        System.out.println(Arrays.toString(arguments.getSourceArgs()));
        System.out.println(arguments.getOptionNames());
        System.out.println(arguments.getNonOptionArgs());
    }
}
```

Nếu cần phân biệt chính xác phần tử nào là option và phần tử nào là positional argument theo quy tắc của Spring Boot, dùng API của `ApplicationArguments`. Nếu cần văn bản gốc người dùng gõ, API này không cung cấp dữ liệu đó.

## 4. Vì sao không thể khôi phục chuỗi gốc từ `args`?

Nhiều cách viết khác nhau có thể tạo ra cùng một danh sách đối số. Ví dụ trong Bash:

```bash
java ArgumentProbe search --query "spring shell guide"
java ArgumentProbe search --query 'spring shell guide'
java ArgumentProbe search --query spring\ shell\ guide
```

Các cách viết trên đều có thể tạo ra cùng giá trị đối số cuối cùng là `spring shell guide`. Sau khi Bash xử lý quote removal và escaping, Java không còn thông tin để biết người dùng đã chọn cách viết nào.

Việc ghép lại mảng bằng dấu cách cũng không khôi phục được dữ liệu ban đầu. Hai mảng khác nhau:

```text
["spring shell", "guide"]
["spring", "shell guide"]
```

đều có thể trở thành cùng một chuỗi nếu dùng `String.join(" ", args)`:

```text
spring shell guide
```

Khi ghép, ranh giới giữa phần tử đã mất. Tương tự, các dấu nháy, dấu escape, wildcard trước khi mở rộng và biểu thức biến môi trường cũng không được lưu lại trong `args`.

Vì vậy:

- Không dùng `String.join(" ", args)` rồi coi kết quả là dòng lệnh gốc.
- Không cố suy luận người dùng đã dùng loại dấu nháy nào từ giá trị trong `args`.
- Nếu ứng dụng cần lưu lại chính xác văn bản đầu vào, hãy thu thập văn bản ở lớp đang nhận nó, ví dụ input line trong interactive shell, hoặc yêu cầu người gọi truyền riêng một trường dữ liệu có định dạng rõ ràng.

## 5. Shell hệ điều hành đã xử lý những gì?

Shell hệ điều hành không chỉ tách từ theo khoảng trắng. Tùy loại shell, nó có thể thay thế biến, mở rộng wildcard, thực thi command substitution, xử lý pipe và redirection, hoặc diễn giải ký tự đặc biệt.

### Bash và các shell kiểu POSIX

Bash thực hiện các bước như brace expansion, tilde expansion, parameter expansion, command substitution, arithmetic expansion, word splitting, pathname expansion và quote removal trước khi thực thi command.

Ví dụ:

```bash
QUERY="spring shell"
java -jar catalog-cli.jar search --query "$QUERY"
```

Giá trị của `$QUERY` được thay thế trước khi chương trình Java được khởi chạy. Dấu nháy kép giữ giá trị chứa khoảng trắng thành một word duy nhất; dấu nháy không được truyền như ký tự dữ liệu.

So sánh:

```bash
java -jar catalog-cli.jar search --query $QUERY
java -jar catalog-cli.jar search --query "$QUERY"
```

Ở dòng đầu, giá trị không được đặt trong dấu nháy kép nên có thể bị word splitting và pathname expansion. Ở dòng thứ hai, kết quả mở rộng được giữ trong một đối số. Nếu biến chứa `spring shell`, dòng đầu có thể tạo hai đối số giá trị `spring` và `shell`, trong khi dòng thứ hai tạo một đối số `spring shell`.

Một ví dụ khác với wildcard:

```bash
java -jar catalog-cli.jar import *.csv
```

Nếu thư mục hiện tại có các file CSV, Bash có thể mở rộng `*.csv` thành danh sách tên file trước khi Java nhận đối số. Nếu muốn truyền chính chuỗi `*.csv` cho ứng dụng để ứng dụng tự xử lý, cần quote hoặc escape wildcard:

```bash
java -jar catalog-cli.jar import '*.csv'
```

### PowerShell trên Windows

PowerShell phân tích command thành token ở chế độ expression hoặc argument. Dấu nháy đơn tạo chuỗi literal; dấu nháy kép cho phép nội suy biến và biểu thức. Với native executable, PowerShell chuyển các đối số đã phân tích thành cách truyền phù hợp cho tiến trình đích.

Ví dụ:

```powershell
$query = "spring shell guide"
java -jar .\catalog-cli.jar search --query "$query"
```

Giá trị biến được nội suy trong chuỗi dấu nháy kép. Dùng dấu nháy đơn nếu muốn giữ `$query` nguyên văn:

```powershell
java -jar .\catalog-cli.jar search --query '$query'
```

Trong PowerShell, backtick (`` ` ``) là ký tự escape của ngôn ngữ. Dấu gạch chéo ngược `\` không phải ký tự escape chung của PowerShell; nó có vai trò riêng trong cách native process nhận chuỗi trên Windows.

PowerShell 7.3 thay đổi cách truyền đối số cho native command và bổ sung `$PSNativeCommandArgumentPassing` với các chế độ `Legacy`, `Standard` và `Windows`. Windows PowerShell 5.1 có hành vi cũ. Vì vậy, script cần xử lý dấu nháy lồng nhau, chuỗi rỗng hoặc ký tự đặc biệt nên được kiểm tra trên đúng phiên bản PowerShell dùng trong môi trường triển khai.

### cmd.exe

`cmd.exe` có quy tắc quote và escape khác Bash và PowerShell. Dấu nháy kép thường được dùng để nhóm đường dẫn hoặc giá trị có khoảng trắng; dấu nháy đơn không đóng vai trò quote như trong Bash.

Ví dụ:

```bat
java -jar catalog-cli.jar search --query "spring shell guide"
```

Không sao chép nguyên xi cú pháp escape của Bash hoặc PowerShell sang batch file. Nếu script cần xử lý nhiều lớp quote hoặc truyền dữ liệu phức tạp, hãy giảm số lớp phân tích bằng cách dùng file script hoặc chương trình gọi tiến trình với danh sách đối số rõ ràng.

Do Windows tạo process bằng một command-line string, cách executable phân tích dấu nháy và dấu gạch chéo ngược có thể phụ thuộc vào runtime hoặc thư viện mà chương trình sử dụng. Java launcher xử lý quy tắc của nó để tạo `main(String[] args)`; một native executable khác có thể cho kết quả khác khi nhận cùng một chuỗi.

## 6. Dấu nháy thuộc shell nào?

Một ứng dụng Spring Shell có thể có hai lần phân tích khác nhau tùy cách chạy:

| Cách chạy | Thành phần đọc cú pháp trước | Dấu nháy được xử lý ở đâu? |
|---|---|---|
| Người dùng gõ `search --query "spring shell"` tại prompt Spring Shell | Spring Shell | `CommandParser` của Spring Shell |
| Người dùng chạy `java -jar app.jar search --query "spring shell"` từ Bash | Bash, rồi Java launcher và Spring Shell runner | Bash xử lý quote của dòng khởi chạy; Spring Shell chỉ thấy dữ liệu còn lại |
| Người dùng chạy cùng lệnh từ PowerShell | PowerShell, rồi native argument passing và Java launcher | PowerShell xử lý quote/expansion theo phiên bản; Java nhận đối số sau bước truyền native |
| Một Java process khác gọi CLI bằng `ProcessBuilder` | `ProcessBuilder` và cơ chế tạo process của hệ điều hành | Mỗi phần tử trong danh sách command được dùng làm một đối số theo API |

Trong interactive mode, Spring Shell có thể nhận nguyên văn input line, ví dụ:

```text
shell:>search --query="spring shell guide"
```

`CommandParser.parse(String input)` nhận chuỗi input thô và parser xử lý dấu nháy, khoảng trắng, option cùng argument theo cú pháp Spring Shell. Dấu nháy được dùng để nhóm giá trị sẽ không thuộc nội dung giá trị sau khi parse.

Khi chạy non-interactive, `ShellRunner.run(String[] args)` nhận mảng đối số của tiến trình. API này không cung cấp lại dòng lệnh gốc mà Bash hoặc PowerShell đã nhận. Không nên giả định cách xử lý quote của prompt interactive giống hệt cách runner xử lý mảng đối số khởi chạy; hãy kiểm thử trên đúng runner và phiên bản Spring Shell đang dùng.

## 7. Spring Shell parser xử lý raw input của chính nó

Spring Shell 4 có `CommandParser` để phân tích văn bản command thành `ParsedInput`. Parser mặc định hỗ trợ:

- Tên command và các subcommand nhiều token.
- Option dài dạng `--key=value` hoặc `--key value`.
- Option ngắn dạng `-k=value` hoặc `-k value`.
- Argument vị trí và option xuất hiện theo thứ tự khác nhau.
- Dấu nháy đơn hoặc kép để nhóm giá trị có khoảng trắng trong input line.
- Escape dấu nháy bằng backslash trong giá trị được quote.

Ví dụ input line mà Spring Shell parser có thể xử lý:

```text
search --query="spring shell guide"
search --query='spring shell guide'
search "spring shell guide"
search --query="He said \"hello\""
```

Các cách viết này mô tả quy tắc của parser Spring Shell khi nó nhận được raw input line. Nếu cùng các dấu nháy được dùng ở dòng lệnh khởi chạy từ Bash hoặc PowerShell, shell hệ điều hành có thể loại bỏ chúng trước. Vì thế, không thể lấy ví dụ quote trong prompt Spring Shell rồi mặc định rằng `main(String[] args)` sẽ thấy nguyên văn cùng chuỗi.

Spring Shell 4 cung cấp interface `CommandParser`; nếu cú pháp mặc định không đáp ứng nhu cầu, có thể triển khai parser riêng và đăng ký nó thành bean. Parser tùy chỉnh chỉ kiểm soát bước parse của Spring Shell. Nó không thay đổi cách Bash, PowerShell hoặc Windows tạo đối số cho tiến trình Java.

## 8. Ví dụ command Spring Shell và cách kiểm tra

Giả sử có command tìm kiếm:

```java
@Component
public class SearchCommands {

    @Command(name = "search", description = "Search catalog entries")
    public String search(
            @Option(longName = "query", description = "Text to search") String query) {
        return "Searching for: [" + query + "]";
    }
}
```

Trong prompt tương tác Spring Shell, nhập:

```text
shell:>search --query="spring shell guide"
Searching for: [spring shell guide]
```

Để kiểm tra đối số của process khi khởi chạy ứng dụng, in `args` ngay trong `main` trước khi gọi `SpringApplication.run`:

```java
@SpringBootApplication
public class CatalogCliApplication {

    public static void main(String[] args) {
        for (int i = 0; i < args.length; i++) {
            System.out.printf("args[%d]=<%s>%n", i, args[i]);
        }
        SpringApplication.run(CatalogCliApplication.class, args);
    }
}
```

Chạy từ PowerShell:

```powershell
java -jar .\catalog-cli.jar search --query 'spring shell guide'
```

Chạy từ Bash:

```bash
java -jar ./catalog-cli.jar search --query 'spring shell guide'
```

Quan sát `args` để xác nhận ranh giới thực tế. Sau đó kiểm tra command ở non-interactive mode trên đúng phiên bản Spring Shell. Nếu giá trị có khoảng trắng, dấu nháy lồng nhau hoặc ký tự đặc biệt, hãy thêm kiểm thử đầu cuối thay vì suy luận từ cách dòng lệnh được viết.

## 9. Gọi CLI từ một Java process khác

Nếu một ứng dụng Java cần khởi chạy CLI khác, dùng `ProcessBuilder` với danh sách đối số. Tránh ghép toàn bộ command thành một chuỗi rồi phụ thuộc vào shell bên ngoài phân tích lại.

```java
import java.io.IOException;

public class CliProcessLauncher {

    public static int runCatalogCli() throws IOException, InterruptedException {
        ProcessBuilder processBuilder = new ProcessBuilder(
                "java",
                "-jar",
                "catalog-cli.jar",
                "search",
                "--query",
                "spring shell guide"
        );

        processBuilder.inheritIO();
        Process process = processBuilder.start();
        return process.waitFor();
    }
}
```

Mỗi phần tử trong danh sách là một thành phần của command: executable, tùy chọn JVM, tên JAR hoặc một đối số ứng dụng. Giá trị `spring shell guide` là một phần tử duy nhất; `ProcessBuilder` chịu trách nhiệm chuyển danh sách này sang cơ chế tạo process của hệ điều hành.

Không dùng cách sau cho dữ liệu có khoảng trắng:

```java
Runtime.getRuntime().exec(
        "java -jar catalog-cli.jar search --query spring shell guide");
```

Chuỗi này phụ thuộc vào quy tắc phân tích của nền tảng và overload được gọi. Nó không biểu đạt rõ ranh giới giữa `spring shell guide` là một đối số hay ba đối số. Dùng `ProcessBuilder` với từng phần tử riêng giúp ý định của chương trình rõ ràng hơn.

## 10. Khi cần giữ nguyên văn bản lệnh, hãy lưu nó ở đúng lớp

Nếu yêu cầu nghiệp vụ cần lưu lại chính xác nội dung người dùng nhập, không thể chỉ lưu `String[] args` rồi gọi đó là raw command line. Có một số lựa chọn:

1. **Trong interactive Spring Shell:** thu thập input line trước hoặc tại lớp đọc terminal, nếu ứng dụng thực sự cần lưu dấu nháy và cách viết gốc. Không chỉ lưu `ParsedInput` vì đó là kết quả sau parse.
2. **Trong non-interactive mode:** yêu cầu caller gửi thêm một trường dữ liệu riêng nếu cần lưu câu lệnh gốc, hoặc ghi lệnh vào script file để giữ nguyên văn bản từng dòng.
3. **Khi Java process gọi Java process khác:** lưu danh sách đối số có cấu trúc riêng, chẳng hạn JSON array, thay vì ghép thành một chuỗi không có quy tắc quoting rõ ràng.

Spring Shell `NonInteractiveShellRunner` hỗ trợ chạy script bằng cách truyền tên file có tiền tố `@` làm đối số. Ví dụ:

```bash
java -jar catalog-cli.jar @commands.txt
```

Nội dung `commands.txt` có thể chứa các dòng lệnh Spring Shell:

```text
search --query="spring shell guide"
search --query='command parser'
```

Ở đây, dấu nháy được lưu trong file và được Spring Shell parser xử lý khi đọc từng dòng. File script phù hợp khi cần chạy nhiều command hoặc cần duy trì cách viết command có quote qua các lần chạy. Kiểm tra cú pháp script và encoding file trong môi trường triển khai thực tế.

## 11. Lỗi thường gặp khi nhầm chuỗi gốc và argv

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Java nhận hai đối số `spring` và `shell` thay vì một | Giá trị chứa khoảng trắng không được quote ở shell hệ điều hành | Quote giá trị theo đúng cú pháp của Bash, PowerShell hoặc `cmd.exe` |
| `args` không còn dấu nháy đã gõ | Shell đã dùng dấu nháy để nhóm token và loại bỏ chúng | Đây là hành vi bình thường; không tìm dấu nháy trong `args` |
| Dùng `String.join(" ", args)` nhưng không dựng lại được lệnh ban đầu | Ranh giới giữa các phần tử và cách quote ban đầu đã mất | Giữ `String[]` như dữ liệu có cấu trúc hoặc lưu raw input ở lớp nhận nó |
| Wildcard truyền vào Java thành nhiều tên file | Bash mở rộng pathname pattern trước khi chạy Java | Quote wildcard nếu muốn truyền nguyên mẫu cho ứng dụng |
| Biến môi trường xuất hiện thành giá trị trong đối số | Shell đã nội suy biến trước khi tạo process | Dùng quote phù hợp hoặc truyền dữ liệu theo cơ chế cấu hình riêng |
| Script chạy khác nhau giữa Windows PowerShell 5.1 và PowerShell 7.3+ | Cách truyền đối số native đã thay đổi theo phiên bản PowerShell | Kiểm tra `$PSNativeCommandArgumentPassing` và chạy test trên đúng phiên bản |
| Prompt Spring Shell parse được quote nhưng non-interactive chạy sai | Hai đường chạy nhận đầu vào ở hai dạng khác nhau: raw input line và `String[]` | Kiểm thử đúng `ShellRunner`; cân nhắc dùng script file `@commands.txt` cho lệnh phức tạp |
| Dùng `args.toString()` mà không thấy từng giá trị | `toString()` của mảng không in nội dung phần tử | Dùng vòng lặp hoặc `Arrays.toString(args)` để debug |

## 12. Checklist khi thiết kế và kiểm thử đối số

- [ ] Đã phân biệt văn bản người dùng gõ với `String[] args` của Java.
- [ ] Đã xác định shell hệ điều hành thực tế: Bash, PowerShell hay `cmd.exe`.
- [ ] Đã quote giá trị có khoảng trắng theo đúng cú pháp của shell đó.
- [ ] Đã kiểm tra biến môi trường, wildcard, command substitution và ký tự đặc biệt có bị shell mở rộng không.
- [ ] Đã in từng phần tử `args` để xác nhận số lượng và ranh giới đối số.
- [ ] Không giả định dấu nháy gõ ở terminal sẽ còn nguyên trong `args`.
- [ ] Không dùng `String.join(" ", args)` để khôi phục chuỗi lệnh gốc.
- [ ] Đã phân biệt parser input line của Spring Shell với `ShellRunner.run(String[] args)`.
- [ ] Đã kiểm thử command non-interactive với giá trị có khoảng trắng và dấu nháy trên đúng phiên bản shell hệ điều hành.
- [ ] Dùng `ProcessBuilder` với danh sách đối số khi Java gọi một tiến trình khác.
- [ ] Dùng script file hoặc định dạng dữ liệu có cấu trúc nếu cần lưu và tái chạy đầu vào phức tạp.

## Tài liệu tham khảo

1. [Java Tutorials – Command-Line Arguments](https://docs.oracle.com/javase/tutorial/essential/environment/cmdLineArgs.html) – cách Java chuyển đối số vào `main(String[] args)`.
2. [Java Language Specification – JVM Startup](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-12.html#jls-12.1) – quy tắc khởi động và truyền mảng chuỗi vào `main`.
3. [Java – ProcessBuilder](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ProcessBuilder.html) – tạo process bằng danh sách executable và đối số.
4. [Bash Reference Manual – Shell Expansions](https://www.gnu.org/software/bash/manual/bash.html#Shell-Expansions) và [Quote Removal](https://www.gnu.org/software/bash/manual/html_node/Quote-Removal.html) – expansion, word splitting và loại bỏ dấu nháy.
5. [Microsoft Learn – about_Parsing](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_parsing) – PowerShell tokenization, argument mode và native argument passing.
6. [Microsoft Learn – CommandLineToArgvW](https://learn.microsoft.com/en-us/windows/win32/api/shellapi/nf-shellapi-commandlinetoargvw) – một quy tắc phân tích command-line string trên Windows.
7. [Spring Shell 4 – Command Syntax](https://docs.spring.io/spring-shell/reference/commands/syntax.html) – cú pháp option, argument, quote và escape của Spring Shell parser.
8. [Spring Shell 4 – CommandParser API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/CommandParser.html) – parser nhận raw input string và trả về `ParsedInput`.
9. [Spring Shell 4 – ShellRunner API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/ShellRunner.html) và [NonInteractiveShellRunner API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/NonInteractiveShellRunner.html) – runner nhận `String[] args` và thực thi command/script.

Khi xử lý lỗi đối số, hãy quan sát dữ liệu ở ranh giới đầu tiên mà ứng dụng kiểm soát được: `String[] args` trong Java hoặc raw input line trong Spring Shell interactive mode. Nếu dữ liệu đã thay đổi trước ranh giới đó, cần sửa cách gọi ở shell hệ điều hành hoặc cách chương trình cha tạo process; parser Spring Shell không thể khôi phục thông tin đã bị loại bỏ ở bước trước.
