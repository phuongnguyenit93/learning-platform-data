# Completion không hoạt động vì runner không dùng JLine

Một ứng dụng Spring Shell có thể khởi động thành công, chạy command bình thường và thậm chí đã khai báo `ValueProvider` hoặc `CompletionProvider`, nhưng nhấn Tab vẫn không hiện gợi ý. Một nguyên nhân thường gặp là ứng dụng đang chạy bằng shell runner không tích hợp JLine.

Completion có hai phần riêng:

1. **Nguồn gợi ý:** Spring Shell xác định command, option và các giá trị có thể điền. Phần này dùng command registry, completion resolver hoặc provider.
2. **Trải nghiệm nhập lệnh:** một line editor nhận phím Tab, phân tích dòng hiện tại, yêu cầu Spring Shell tìm gợi ý rồi hiển thị các proposal. Trong Spring Shell, trải nghiệm Tab tương tác này do shell dựa trên JLine cung cấp.

Provider chỉ tạo danh sách gợi ý. Nó không tự cài đặt phím Tab hoặc biến một runner non-interactive thành REPL. Vì vậy, hãy kiểm tra runner và dependency trước khi sửa logic của provider.

## 1. Hiểu đường đi của một lần nhấn Tab

Khi người dùng gõ `inventory deploy --environment de` rồi nhấn Tab trong một shell tương tác dùng JLine, luồng xử lý khái quát như sau:

~~~text
Người dùng nhấn Tab
        |
        v
JLine line editor nhận phím và dòng hiện tại
        |
        v
Parser xác định vị trí con trỏ và token đang nhập
        |
        v
Spring Shell tra command, option và completion provider
        |
        v
Completion proposals được trả về
        |
        v
JLine hiển thị gợi ý hoặc hoàn tất token
~~~

Nếu ứng dụng chỉ chạy command từ tham số tiến trình, đọc script hoặc dùng một console runner không có JLine, luồng nhập lệnh tương tác ở trên không tồn tại. Spring Shell vẫn có thể phân tích và thực thi command, nhưng không có line editor JLine để nhận Tab.

Phân biệt ba khả năng sau:

| Khả năng | Chức năng | Có cần JLine interactive runner? |
|---|---|---|
| Command completion trong REPL | Nhấn Tab để gợi ý tên command và option | Có |
| Completion giá trị option | Gợi ý enum, file, môi trường hoặc giá trị nghiệp vụ khi đang nhập command trong REPL | Có |
| Completion tại prompt của Bash | Nhấn Tab ở terminal OS trước khi chạy command | Dùng script completion của Bash; không phải JLine REPL |

Không nên dùng kết quả của một loại completion để kết luận loại còn lại đã hoạt động.

## 2. Xác định Spring Shell version và runner đang được dùng

Đầu tiên hãy kiểm tra version thực tế trong runtime. Cấu hình runner của Spring Shell 3.x khác đáng kể so với 4.x.

### 2.1. Spring Shell 3.3.x

Spring Shell 3.3 có ba runner:

- `InteractiveShellRunner`: mở REPL tương tác dựa trên JLine.
- `NonInteractiveShellRunner`: thực thi command từ tham số tiến trình rồi kết thúc.
- `ScriptShellRunner`: đọc và thực thi script theo cơ chế script của Spring Shell.

Thay đổi quan trọng từ 3.3.x là chỉ `NonInteractiveShellRunner` được bật mặc định. Những phiên bản đến 3.2.x bật các runner mặc định rộng hơn. Vì vậy, ứng dụng nâng cấp lên 3.3 có thể vẫn chạy command một lần nhưng không tự mở REPL như trước.

Để bật REPL, cấu hình:

~~~yaml
spring:
  shell:
    interactive:
      enabled: true
~~~

Khi chạy ứng dụng không truyền command làm tham số tiến trình, `InteractiveShellRunner` có thể mở phiên shell để người dùng nhập command và dùng Tab.

Nếu ứng dụng cần cả REPL và xử lý command/script tự động, hãy bật các runner phù hợp với quy trình triển khai. Không tắt non-interactive mode một cách máy móc nếu pipeline hoặc script đang dựa vào nó.

Các thuộc tính runner trong 3.3.x:

| Thuộc tính | Mục đích |
|---|---|
| `spring.shell.interactive.enabled` | Bật/tắt `InteractiveShellRunner` |
| `spring.shell.noninteractive.enabled` | Bật/tắt `NonInteractiveShellRunner` |
| `spring.shell.script.enabled` | Bật/tắt `ScriptShellRunner` |

Có thể đặt thuộc tính trong `application.yml`, profile, biến môi trường hoặc tham số cấu hình Spring Boot. Ví dụ dùng biến môi trường:

~~~powershell
$env:SPRING_SHELL_INTERACTIVE_ENABLED = "true"
java -jar .\inventory-shell.jar
~~~

Trên Bash:

~~~bash
SPRING_SHELL_INTERACTIVE_ENABLED=true java -jar inventory-shell.jar
~~~

Nếu chỉ muốn bật cho môi trường phát triển, đặt cấu hình trong profile riêng:

~~~yaml
# application-dev.yml
spring:
  shell:
    interactive:
      enabled: true
~~~

Khởi chạy với profile:

~~~bash
java -jar inventory-shell.jar --spring.profiles.active=dev
~~~

Khi đã mở REPL, thử `help`, gõ một phần tên command rồi nhấn Tab. Nếu command và option mặc định được gợi ý, runner và JLine đã hoạt động; lúc đó mới kiểm tra provider riêng.

### 2.2. Spring Shell 4.x

Spring Shell 4 thay đổi cách đóng gói và lựa chọn runner. `spring-shell-core` không còn phụ thuộc JLine. Ba implementation chính là:

- `SystemShellRunner`: shell tương tác dựa trên `java.io.Console` của JDK.
- `JLineShellRunner`: shell tương tác dựa trên JLine.
- `NonInteractiveShellRunner`: thực thi command hoặc script mà không mở REPL tương tác.

`SystemShellRunner` có thể đọc command tương tác, nhưng không cung cấp các tính năng JLine như history, Tab completion và rich text formatting. Do đó, việc thấy prompt và gõ command thành công chưa chứng minh ứng dụng đang dùng JLine.

Trong Spring Boot, cách đơn giản nhất để có cấu hình JLine là dùng Spring Shell starter:

~~~xml
<dependency>
    <groupId>org.springframework.shell</groupId>
    <artifactId>spring-shell-starter</artifactId>
</dependency>
~~~

Với Gradle:

~~~groovy
dependencies {
    implementation("org.springframework.shell:spring-shell-starter")
}
~~~

Spring Shell starter cung cấp cấu hình tương tác dùng JLine. Nếu ứng dụng chỉ dùng các module core riêng, hãy thêm module JLine:

~~~xml
<dependency>
    <groupId>org.springframework.shell</groupId>
    <artifactId>spring-shell-jline</artifactId>
</dependency>
~~~

Với Gradle:

~~~groovy
dependencies {
    implementation("org.springframework.shell:spring-shell-jline")
}
~~~

Trong ứng dụng không dùng Spring Boot hoặc tự quản lý cấu hình runner, ngoài dependency JLine còn phải đăng ký `JLineShellRunner` làm runner được sử dụng. Chỉ thêm JLine vào classpath nhưng vẫn khởi chạy một runner khác thì Tab completion vẫn không xuất hiện.

Spring Shell 4 yêu cầu nền tảng Spring Boot 4/Spring Framework 7 khi tích hợp theo hướng Spring Boot. Không ghép dependency Spring Shell 4 vào ứng dụng Spring Boot 3 chỉ để lấy JLine; hãy nâng cấp theo hướng dẫn migration tương ứng.

Thuộc tính `spring.shell.interactive.enabled` trong 4.x có mặc định là `true`. Đặt thành `false` sẽ chuyển ứng dụng sang non-interactive mode để chạy command từ tham số tiến trình rồi thoát:

~~~yaml
spring:
  shell:
    interactive:
      enabled: false
~~~

Cấu hình này phù hợp cho job hoặc automation. Nó không phải cách sửa Tab completion trong REPL vì REPL đã bị tắt.

### 2.3. So sánh nhanh theo phiên bản

| Nội dung | Spring Shell 3.3.x | Spring Shell 4.x |
|---|---|---|
| Runner JLine tương tác | `InteractiveShellRunner` | `JLineShellRunner` |
| Runner console cơ bản | Không có runner tương ứng trong bộ runner 3.3.x | `SystemShellRunner` |
| Runner không tương tác | `NonInteractiveShellRunner` | `NonInteractiveShellRunner` |
| Mặc định tương tác | Chỉ non-interactive runner được bật mặc định | Interactive mode được bật mặc định |
| Cách bật JLine | Bật `spring.shell.interactive.enabled=true` và dùng cấu hình/dependency Spring Shell có JLine | Dùng starter có JLine hoặc thêm `spring-shell-jline` và chọn `JLineShellRunner` |
| Annotation command | `@ShellComponent`, `@ShellMethod`, `@ShellOption` | `@Command`, `@Option`, `@Argument` |

Khi chẩn đoán, không sao chép cấu hình runner của 3.x sang 4.x mà không kiểm tra migration guide.

## 3. Kiểm tra dependency có chứa JLine

Một dự án có thể khai báo Spring Shell core nhưng thiếu module JLine. Command vẫn đăng ký và chạy được vì command registry không đồng nghĩa với JLine line editor.

Với Maven, xem dependency tree:

~~~bash
./mvnw dependency:tree -Dincludes=org.springframework.shell
~~~

Với Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Tìm các artifact phù hợp với version đang dùng:

| Artifact | Vai trò |
|---|---|
| `spring-shell-starter` | Starter Spring Shell cho ứng dụng Spring Boot; trong 4.x cung cấp cấu hình JLine tương tác |
| `spring-shell-core` | API lõi, command model và chức năng không phụ thuộc JLine |
| `spring-shell-jline` | Tích hợp JLine, line editor và completion tương tác trong 4.x |
| `spring-shell-core-autoconfigure` | Auto-configuration cho core trong cấu trúc module 4.x |

Tên và quan hệ phụ thuộc thay đổi theo major version. Hãy dùng BOM hoặc dependency management của đúng Spring Shell release để tránh trộn các module khác version.

Nếu dependency tree chỉ có core mà không có JLine, kiểm tra xem ứng dụng có chủ ý dùng `SystemShellRunner` hay không. Nếu mục tiêu là Tab completion trong REPL, thêm JLine và cấu hình runner phù hợp.

## 4. Xác nhận ứng dụng đang chạy trong terminal tương tác

JLine cần môi trường nhập/xuất terminal phù hợp. Một số cách khởi chạy khiến ứng dụng không có terminal tương tác:

- Chạy command một lần bằng tham số tiến trình rồi ứng dụng kết thúc.
- Redirect standard input hoặc output vào file/pipe.
- Chạy trong môi trường CI không cấp pseudo-terminal.
- Chạy từ console của IDE không chuyển tiếp đầy đủ phím điều khiển.
- Khởi động một runner non-interactive hoặc `SystemShellRunner` trong khi mong đợi tính năng JLine.

Hãy kiểm tra bằng một terminal thực:

1. Mở PowerShell/Windows Terminal, Bash hoặc terminal tương ứng của hệ điều hành.
2. Chạy JAR mà không truyền command nghiệp vụ ở cuối lệnh.
3. Đợi prompt của Spring Shell xuất hiện.
4. Gõ một phần tên command có sẵn, chẳng hạn `inv`, rồi nhấn Tab.
5. Thử hoàn tất option sau khi gõ tên command.

Ví dụ:

~~~text
shell:>inv<Tab>
inventory

shell:>inventory <Tab>
list
show
deploy
~~~

Kết quả thực tế phụ thuộc các command đã đăng ký. Nếu Tab được chèn như một ký tự tab, bị terminal hiển thị thành ký tự điều khiển hoặc không có phản hồi, kiểm tra runner và terminal trước khi sửa provider.

`System.console()` trả về `null` có thể là một dấu hiệu môi trường không có Java Console, nhưng không nên dùng riêng giá trị này để kết luận JLine có hoạt động hay không. JLine có thể tạo terminal qua cơ chế riêng. Cách xác nhận tốt hơn là kiểm tra dependency/runner và thử trực tiếp trong terminal tương tác.

## 5. Kiểm tra completion mặc định trước khi kiểm tra provider riêng

Spring Shell có thể gợi ý tên command và option đã đăng ký mà không cần custom provider. Dùng một số phép thử đơn giản:

| Nội dung nhập | Kết quả mong đợi |
|---|---|
| Một phần tên command | Gợi ý command phù hợp |
| Tên command và dấu cách | Gợi ý option hoặc đối số tiếp theo nếu có |
| Một phần tên option | Gợi ý tên option |
| Giá trị của enum option | Gợi ý giá trị enum nếu kiểu và provider hỗ trợ |
| Đường dẫn file | Gợi ý file/thư mục nếu dùng file provider |

Nếu tất cả gợi ý mặc định đều không hoạt động, nguyên nhân thường nằm ở runner, JLine, terminal hoặc chế độ tương tác.

Nếu gợi ý tên command và option hoạt động nhưng giá trị riêng của một option không xuất hiện, lúc đó hãy kiểm tra custom provider.

## 6. Kiểm tra ValueProvider trong Spring Shell 3.x

Trong mô hình annotation của Spring Shell 3.x, `ValueProvider` tạo các giá trị gợi ý cho tham số được đánh dấu bằng `@ShellOption(valueProvider = ...)`.

Ví dụ gợi ý môi trường triển khai:

~~~java
import java.util.List;

import org.springframework.stereotype.Component;
import org.springframework.shell.completion.CompletionContext;
import org.springframework.shell.completion.CompletionProposal;
import org.springframework.shell.standard.ValueProvider;

@Component
public class EnvironmentValueProvider implements ValueProvider {

    @Override
    public List<CompletionProposal> complete(
            CompletionContext completionContext) {
        return List.of(
                new CompletionProposal("dev"),
                new CompletionProposal("staging"),
                new CompletionProposal("production"));
    }
}
~~~

Gắn provider vào tham số command:

~~~java
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.standard.ShellOption;

@ShellComponent
public class DeploymentCommands {

    @ShellMethod(key = "inventory deploy")
    public String deploy(
            @ShellOption(valueProvider = EnvironmentValueProvider.class)
            String environment) {
        return "Deploying to " + environment;
    }
}
~~~

Khi JLine REPL hoạt động, thử:

~~~text
shell:>inventory deploy --environment <Tab>
dev
staging
production
~~~

Nếu provider có gọi database hoặc API để lấy giá trị, hãy ghi log ở mức debug trong phương thức `complete()` để xác định nó có được gọi hay không. Không ghi password, token hoặc dữ liệu nhạy cảm vào log completion.

Kiểm tra các điểm sau:

- Provider có được Spring đăng ký thành bean không?
- `@ShellOption` có tham chiếu đúng class provider không?
- Method `complete()` có trả danh sách `CompletionProposal` không?
- Completion context có đang ở đúng tham số mà provider phụ trách không?
- Provider có ném exception khi truy vấn dữ liệu không?
- JLine runner có thực sự được dùng không?

Một provider trả danh sách rỗng không phải lỗi runner. Ngược lại, provider trả danh sách đầy đủ nhưng runner không có JLine thì người dùng vẫn không nhận được trải nghiệm Tab trong REPL.

## 7. Kiểm tra CompletionProvider trong Spring Shell 4.x

Spring Shell 4 gom completion ở cấp command bằng `CompletionProvider`. Định nghĩa provider dưới dạng bean và tham chiếu tên bean từ annotation `@Command`.

Ví dụ:

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.completion.CompletionProposal;
import org.springframework.shell.core.command.completion.CompletionProvider;

@Configuration
class CompletionConfiguration {

    @Bean
    CompletionProvider environmentCompletionProvider() {
        return completionContext -> List.of(
                new CompletionProposal("dev"),
                new CompletionProposal("staging"),
                new CompletionProposal("production"));
    }
}
~~~

Command dùng provider:

~~~java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class DeploymentCommands {

    @Command(
            name = "inventory deploy",
            completionProvider = "environmentCompletionProvider")
    public String deploy(
            @Option(longName = "environment") String environment) {
        return "Deploying to " + environment;
    }
}
~~~

Đoạn code minh họa API annotation mới của Spring Shell 4. Không dùng `@ShellComponent`, `@ShellMethod` hoặc `@ShellOption` từ mô hình cũ trong ví dụ 4.x vì các annotation legacy đã bị loại bỏ.

CompletionProvider chỉ trả về proposal. Ứng dụng vẫn cần runner tương tác dựa trên JLine để người dùng nhấn Tab và nhìn thấy kết quả.

## 8. Phân biệt Tab completion trong REPL với completion của Bash

Một nguyên nhân gây nhầm lẫn là người dùng đang ở prompt của Bash/PowerShell và mong Spring Shell tự gợi ý command của ứng dụng.

Ví dụ hai vị trí khác nhau:

~~~text
# Tab trong REPL của Spring Shell
shell:>inventory de<Tab>
deploy

# Tab tại prompt của Bash để hoàn tất lệnh chạy JAR
$ java -jar inventory-shell.jar inv<Tab>
~~~

Trường hợp đầu là completion bên trong REPL, do JLine xử lý.

Trường hợp thứ hai là completion của shell hệ điều hành. Spring Shell 3.x có command tích hợp để sinh script Bash:

~~~text
shell:>completion bash
~~~

Script này cần được nạp vào Bash theo hướng dẫn của command hoặc tài liệu phiên bản tương ứng. Nó cho phép Bash gợi ý lệnh tại prompt OS; nó không làm cho một tiến trình non-interactive tự có JLine REPL.

Theo tài liệu Spring Shell 3.3, completion tích hợp ở cấp command line được hỗ trợ cho Bash. Nếu ứng dụng chạy bằng một lệnh một lần hoặc trong script, hãy chọn cơ chế completion của OS shell thay vì cố bật JLine REPL.

## 9. Chẩn đoán theo triệu chứng

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng xử lý |
|---|---|---|
| Command chạy một lần rồi tiến trình thoát | `NonInteractiveShellRunner` đang xử lý tham số | Bật interactive runner nếu cần REPL |
| Spring Shell 3.3 nâng cấp xong không còn prompt như trước | 3.3.x chỉ bật non-interactive runner mặc định | Đặt `spring.shell.interactive.enabled=true` |
| Có prompt nhưng Tab không gợi ý, history cũng thiếu | Runner không dùng JLine | Dùng `InteractiveShellRunner` ở 3.x hoặc `JLineShellRunner` ở 4.x |
| Spring Shell 4 có prompt nhưng không có Tab | Đang dùng `SystemShellRunner` | Thêm `spring-shell-jline` hoặc dùng starter có JLine |
| Provider không được gọi | Chưa gắn đúng provider hoặc completion context không khớp | Kiểm tra annotation, bean và vị trí con trỏ |
| Provider được gọi nhưng không có gợi ý | Trả danh sách rỗng hoặc lỗi truy vấn | Kiểm tra dữ liệu và exception trong provider |
| Command và option có gợi ý nhưng giá trị không có | Custom provider cho giá trị chưa được cấu hình đúng | Kiểm tra `ValueProvider`/`CompletionProvider` |
| Tab hoạt động trong REPL nhưng không hoạt động ở Bash prompt | Đang mong dùng nhầm cơ chế completion | Cài script completion cho OS shell |
| Hoạt động trong terminal thật nhưng không hoạt động trong IDE | IDE console không chuyển tiếp đầy đủ thao tác terminal | Thử terminal ngoài IDE hoặc cấu hình console tương thích |
| Chạy được ở local nhưng không ở CI | CI không cấp terminal/pseudo-terminal | Dùng non-interactive command hoặc cấp pseudo-terminal nếu cần kiểm thử REPL |

## 10. Quy trình sửa lỗi có thứ tự

Thực hiện theo thứ tự sau để tránh thay đổi provider khi nguyên nhân nằm ở runner:

1. Xác định version Spring Shell thực tế.
2. Xem dependency tree và xác nhận module JLine có trong runtime classpath nếu cần Tab completion.
3. Xác định runner đang được dùng: non-interactive, system console hay JLine interactive.
4. Với Spring Shell 3.3.x, bật `spring.shell.interactive.enabled=true` cho môi trường cần REPL.
5. Với Spring Shell 4.x, dùng starter có JLine hoặc thêm `spring-shell-jline` và chọn `JLineShellRunner`.
6. Chạy ứng dụng từ terminal tương tác, không truyền command một lần nếu mục tiêu là mở REPL.
7. Thử Tab với tên command và option mặc định.
8. Chỉ khi completion mặc định hoạt động mới kiểm tra custom `ValueProvider` hoặc `CompletionProvider`.
9. Nếu muốn completion ở prompt Bash, tạo và nạp script completion của OS shell.
10. Kiểm thử lại cả chế độ tương tác lẫn non-interactive để bảo đảm job/script hiện có vẫn chạy đúng.

## 11. Ma trận kiểm thử sau khi sửa

Không chỉ kiểm thử bằng cách nhìn thấy prompt. Hãy xác nhận từng chế độ mà ứng dụng hỗ trợ:

| Kịch bản | Cách kiểm tra | Kết quả mong đợi |
|---|---|---|
| REPL tương tác | Chạy JAR không kèm command nghiệp vụ | Prompt xuất hiện và tiếp tục chờ input |
| Completion command | Gõ một phần tên command rồi Tab | Tên command được gợi ý |
| Completion option | Gõ một phần option rồi Tab | Option hợp lệ được gợi ý |
| Completion giá trị | Đặt con trỏ sau option cần provider rồi Tab | Giá trị do provider trả về được hiển thị |
| History | Chạy một command rồi dùng phím điều hướng history | History hoạt động nếu runner JLine được chọn |
| Command non-interactive | Truyền command và option qua tham số tiến trình | Command chạy và tiến trình kết thúc |
| Script | Chạy script theo cơ chế runner của version | Các dòng được thực thi theo thứ tự |
| Bash completion | Nạp script completion và nhấn Tab ở prompt Bash | Bash gợi ý lệnh theo script |
| CI không có TTY | Chạy command tự động với input/output redirect | Command không chờ REPL vô hạn |

Kiểm thử command bằng `ShellTestClient` hoặc gọi trực tiếp method có thể xác nhận logic command, nhưng không chứng minh phím Tab của JLine hoạt động. Cần ít nhất một smoke test qua terminal thật hoặc pseudo-terminal cho chức năng tương tác.

## 12. Ví dụ cấu hình theo hai mục tiêu

### 12.1. Ứng dụng ưu tiên REPL cho người vận hành

Với Spring Shell 3.3.x:

~~~yaml
spring:
  shell:
    interactive:
      enabled: true
    noninteractive:
      enabled: true
~~~

Đảm bảo dependency starter/JLine phù hợp với version 3.x. Khi chạy không kèm command, người vận hành nhận prompt; khi pipeline truyền command làm tham số, runner non-interactive có thể xử lý theo cấu hình.

Với Spring Shell 4.x:

~~~groovy
dependencies {
    implementation("org.springframework.shell:spring-shell-starter")
}
~~~

Starter cung cấp cấu hình JLine tương tác. Nếu tự ghép các module, thêm `spring-shell-jline` và xác nhận `JLineShellRunner` là runner được đăng ký.

### 12.2. Ứng dụng chỉ chạy automation

Nếu ứng dụng chỉ được gọi từ CI, cron hoặc script, không cần bật REPL chỉ để lấy completion. Giữ chế độ non-interactive phù hợp với version và gọi command qua tham số tiến trình hoặc script.

~~~bash
java -jar inventory-shell.jar inventory report --format csv
~~~

Khi đó, completion ở prompt OS cần script dành cho Bash hoặc cơ chế completion riêng của shell hệ điều hành. Không nên để job tự động chờ một prompt tương tác không có người nhập.

## 13. Những cách sửa sai thường gặp

| Cách sửa | Vì sao không giải quyết được nguyên nhân | Cách xử lý đúng |
|---|---|---|
| Viết lại `ValueProvider` nhiều lần | Provider không tạo line editor hoặc phím Tab | Kiểm tra runner JLine trước |
| Thêm `@Component` cho mọi provider | Bean registration không thay đổi runner đang chạy | Xác nhận provider chỉ sau khi completion mặc định hoạt động |
| Bật `spring.shell.interactive.enabled=true` trong Spring Shell 4 nhưng thiếu JLine | Có thể chỉ chuyển sang `SystemShellRunner` | Thêm `spring-shell-jline` hoặc dùng starter |
| Thêm JLine nhưng giữ runner non-interactive | JLine có trên classpath nhưng không được dùng cho REPL | Chọn interactive JLine runner |
| Tắt non-interactive mode trong mọi môi trường | Có thể làm hỏng job và script đang dùng command arguments | Tách cấu hình theo mục tiêu chạy |
| Chỉ kiểm thử method command | Không kiểm tra xử lý phím Tab | Thêm smoke test qua terminal/pseudo-terminal |
| Dùng `completion bash` để sửa Tab trong REPL | Đây là completion ở prompt Bash | Kiểm tra JLine interactive runner |
| Dùng JLine REPL cho pipeline tự động | Pipeline có thể bị chặn chờ input | Dùng non-interactive runner |

## 14. Checklist trước khi kết luận completion đã được sửa

- [ ] Đã xác định đúng Spring Shell major/minor version.
- [ ] Dependency tree có module JLine tương ứng khi cần Tab completion.
- [ ] Runner thực tế là JLine-based interactive runner.
- [ ] Với Spring Shell 3.3.x, interactive runner đã được bật.
- [ ] Với Spring Shell 4.x, không nhầm `SystemShellRunner` với `JLineShellRunner`.
- [ ] Ứng dụng được chạy trong terminal tương tác.
- [ ] Completion command và option mặc định hoạt động.
- [ ] Custom provider là bean và được gắn đúng command/option.
- [ ] Provider trả về proposal hợp lệ và không phát sinh exception.
- [ ] Bash completion được cấu hình riêng nếu cần hoàn tất lệnh ở prompt OS.
- [ ] Non-interactive command và script vẫn hoạt động sau khi thay đổi.

## 15. Tổng kết

Completion không chỉ là một danh sách giá trị do provider tạo ra. Để nhấn Tab và thấy gợi ý trong REPL, ứng dụng phải chạy bằng shell tương tác có line editor JLine.

Với Spring Shell 3.3.x, hãy chú ý thay đổi mặc định runner: chỉ `NonInteractiveShellRunner` được bật mặc định, nên cần bật `spring.shell.interactive.enabled=true` khi muốn REPL. Với Spring Shell 4.x, JLine đã tách khỏi core; dùng Spring Shell starter hoặc thêm `spring-shell-jline` và chọn `JLineShellRunner`. `SystemShellRunner` vẫn có thể nhận command tương tác nhưng không cung cấp Tab completion.

Sau khi xác nhận runner, dependency và terminal, mới kiểm tra `ValueProvider` hoặc `CompletionProvider`. Nếu mục tiêu là gợi ý command ở prompt Bash, hãy cấu hình script completion của Bash; đó là một cơ chế khác với Tab trong REPL Spring Shell.

## Tài liệu tham khảo

- [Spring Shell 3.3.4 — Execution](https://docs.spring.io/spring-shell/reference/3.3/execution.html) — runner, chế độ tương tác và thuộc tính bật `InteractiveShellRunner`.
- [Spring Shell 3.3.4 — Completion](https://docs.spring.io/spring-shell/reference/3.3/completion.html) — `CompletionResolver`, `ValueProvider` và Bash completion.
- [Spring Shell 3.3.4 — Getting Started](https://docs.spring.io/spring-shell/reference/3.3/getting-started.html) — dependency starter và cấu hình interactive runner.
- [Spring Shell 4.0.4 — Execution](https://docs.spring.io/spring-shell/reference/execution.html) — `SystemShellRunner`, `JLineShellRunner`, `NonInteractiveShellRunner`.
- [Spring Shell 4.0.4 — Command Completion](https://docs.spring.io/spring-shell/reference/commands/completion.html) — completion trong JLine-based shell và custom `CompletionProvider`.
- [Spring Shell — v4 Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide) — tách JLine khỏi core, module `spring-shell-jline`, runner và command completion model mới.
