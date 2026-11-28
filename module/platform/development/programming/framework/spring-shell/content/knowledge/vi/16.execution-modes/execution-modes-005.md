# ShellApplicationRunner và chuyển đối số khởi động trong mô hình 3.x

Khi một ứng dụng Spring Shell được khởi chạy bằng `java -jar`, các đối số người dùng truyền vào đi qua Spring Boot trước khi đến bộ thực thi shell. Spring Boot đóng gói chúng trong `ApplicationArguments`. Spring Shell dùng `ShellApplicationRunner` để nhận các đối số khởi động đó và chọn một `ShellRunner` phù hợp, chẳng hạn chạy command một lần, đọc file script hoặc mở phiên tương tác.

Hiểu rõ ranh giới giữa `ApplicationArguments`, `ShellApplicationRunner` và `ShellRunner` giúp tránh mất option khi chuyển đối số, tránh mở nhầm chế độ shell và biết đúng điểm cần mở rộng khi muốn tùy chỉnh cách khởi chạy.

## Luồng khởi động trong Spring Shell 3.x

Trong ứng dụng Spring Boot, phương thức `main` chuyển `String[] args` cho `SpringApplication.run(...)`. Spring Boot tạo `ApplicationContext`, phân tích đối số khởi động thành `ApplicationArguments`, khởi tạo các bean và gọi những bean triển khai `ApplicationRunner` sau khi context đã sẵn sàng. Spring Shell đăng ký một runner chuyên biệt trong giai đoạn này.

```mermaid
flowchart TD
    A[main String[] args] --> B[SpringApplication.run]
    B --> C[Spring Boot tạo ApplicationContext]
    C --> D[Phân tích ApplicationArguments]
    D --> E[ShellApplicationRunner.run]
    E --> F[DefaultShellApplicationRunner]
    F --> G[Danh sách ShellRunner đã sắp xếp]
    G --> H{Runner nào nhận xử lý?}
    H -->|Script| I[ScriptShellRunner đọc file @script]
    H -->|Command args| J[NonInteractiveShellRunner chạy command]
    H -->|Không có runner trước nhận| K[InteractiveShellRunner mở REPL]
    I --> L[Kết thúc tiến trình sau script]
    J --> M[Trả kết quả và kết thúc]
    K --> N[Người dùng tiếp tục nhập lệnh]
```

Ba thành phần có trách nhiệm khác nhau:

| Thành phần | Vai trò |
|---|---|
| `ApplicationArguments` | Đại diện cho các đối số khởi động mà Spring Boot nhận được |
| `ShellApplicationRunner` | Điểm tích hợp giữa vòng đời `ApplicationRunner` của Spring Boot và Spring Shell |
| `ShellRunner` | Thực hiện một cách chạy shell cụ thể dựa trên đối số đầu vào |

Trong mô hình 3.x, `ShellApplicationRunner` là interface chuyên biệt dựa trên `ApplicationRunner`. Chỉ nên có một bean triển khai `ShellApplicationRunner` trong một application context. Mặc định, Spring Shell cung cấp `DefaultShellApplicationRunner`; lớp này nhận danh sách `ShellRunner` và dispatch tới runner đầu tiên có thể xử lý lần khởi chạy hiện tại.

Nếu chỉ cần đọc thêm cấu hình hoặc chuẩn bị dữ liệu lúc ứng dụng khởi động, có thể dùng một bean `ApplicationRunner` riêng. Chỉ thay `ShellApplicationRunner` khi thực sự muốn thay đổi cách Spring Shell chọn và gọi các runner.

## ApplicationArguments của Spring Boot

`ApplicationArguments` thuộc Spring Boot, không phải API riêng của Spring Shell. Nó cung cấp cả mảng đối số gốc lẫn cách nhìn đã phân loại option và non-option:

| Phương thức | Nội dung |
|---|---|
| `getSourceArgs()` | Mảng `String[]` nguyên gốc truyền vào `SpringApplication.run(...)`, giữ nguyên thứ tự và các token |
| `getOptionNames()` | Tập tên các option dạng `--name` hoặc `--name=value` |
| `containsOption(name)` | Kiểm tra có option với tên tương ứng hay không |
| `getOptionValues(name)` | Lấy các giá trị được gắn với option |
| `getNonOptionArgs()` | Danh sách token mà parser Spring Boot phân loại là đối số không phải option |

Ví dụ khởi chạy:

```text
java -jar customer-cli.jar deploy --environment=staging --tag=release-42
```

Spring Boot có thể cung cấp các thông tin tương ứng:

```text
getSourceArgs()
  ["deploy", "--environment=staging", "--tag=release-42"]

getOptionNames()
  ["environment", "tag"]

getOptionValues("environment")
  ["staging"]

getOptionValues("tag")
  ["release-42"]

getNonOptionArgs()
  ["deploy"]
```

`getNonOptionArgs()` không phải bản sao của command line. Các token bắt đầu bằng `--` được Spring Boot phân loại thành option; giá trị có dạng `--key=value` cũng được tách thành tên và giá trị. Vì vậy, nếu cần chuyển toàn bộ cú pháp command cho Spring Shell, hãy giữ nguyên `getSourceArgs()`.

`getSourceArgs()` cũng giữ lại các option cấu hình của Spring Boot, ví dụ `--spring.profiles.active=prod`. Nếu chuyển nguyên mảng này vào `ShellRunner`, các token cấu hình đó vẫn nằm trong đầu vào mà runner nhận. Để tránh nhầm lẫn với option của command, nên đặt cấu hình Boot trong `application.yml`/`application.properties`; nếu bắt buộc truyền qua command line, custom dispatcher cần loại các key Boot đã biết trước khi chuyển phần còn lại cho shell.

Ví dụ đọc đối số khởi động trong một bean Spring Boot:

```java
import java.util.Arrays;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
class StartupArgumentInspector implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("Raw args: " + Arrays.toString(args.getSourceArgs()));

        if (args.containsOption("environment")) {
            System.out.println(
                    "Environment: " + args.getOptionValues("environment"));
        }
    }
}
```

Ví dụ này chỉ minh họa cách một bean đọc cấu hình khởi động. Bean `ApplicationRunner` này vẫn được Spring Boot gọi theo thứ tự `@Order` cùng với runner của Spring Shell; nó không thay thế `ShellApplicationRunner`.

### Vì sao phải giữ mảng đối số gốc?

Giả sử command nhận option `--environment` và `--tag`. Nếu lấy `getNonOptionArgs()`, hai option có thể biến mất khỏi danh sách; command chỉ còn tên `deploy`. Nếu người dùng viết option theo dạng tách token như `--environment staging`, parser Spring Boot còn có thể phân loại `staging` thành non-option. `getSourceArgs()` giữ lại đúng chuỗi token mà người dùng đã truyền để Spring Shell tự phân tích theo cú pháp command của nó.

Quy tắc thực hành:

- Dùng `getOptionValues()` khi cần đọc một cấu hình dành cho Spring Boot hoặc ứng dụng.
- Dùng `getSourceArgs()` khi cần chuyển nguyên dòng đối số cho `ShellRunner`.
- Không dựng lại command bằng cách nối `getNonOptionArgs()` nếu command có named option.
- Không giả định việc Spring Boot nhận diện một token là option đồng nghĩa Spring Shell đã bind token đó vào tham số command.

## ShellApplicationRunner mặc định

Spring Shell cung cấp `DefaultShellApplicationRunner`, triển khai `ShellApplicationRunner`. Nó nhận `List<ShellRunner>` đã được Spring sắp xếp theo thứ tự và hỏi từng runner xem có thể xử lý đầu vào hay không. Runner xử lý xong sẽ báo rằng nó đã nhận trách nhiệm; các runner sau không được gọi cho cùng lần khởi chạy.

Thông thường, không cần tự tạo `ShellApplicationRunner`. Hãy để cấu hình tự động của Spring Shell đăng ký runner mặc định. Cách này giữ nguyên cơ chế ưu tiên và các runner được bật bằng property.

Nếu ứng dụng cần điều phối riêng, có thể cung cấp một bean `ShellApplicationRunner` thay cho bean mặc định. Không đăng ký nhiều `ShellApplicationRunner` cùng lúc vì đây là điểm điều phối duy nhất của shell.

## Ba loại ShellRunner trong mô hình 3.x

Spring Shell 3.x có ba runner chính:

| Runner | Cách hoạt động | Ví dụ sử dụng |
|---|---|---|
| `ScriptShellRunner` | Tìm đối số bắt đầu bằng `@`, đọc file được chỉ định như một script command rồi kết thúc | `java -jar customer-cli.jar @deploy.shell` |
| `NonInteractiveShellRunner` | Nhận command và option từ đối số tiến trình, chạy command mà không mở REPL | `java -jar customer-cli.jar deploy --environment=staging` |
| `InteractiveShellRunner` | Mở vòng lặp REPL để người dùng nhập nhiều command | `java -jar customer-cli.jar` |

Trong các API 3.4.x, thứ tự ưu tiên mặc định là `ScriptShellRunner` (`@Order(-100)`), `NonInteractiveShellRunner` (`@Order(-50)`) rồi `InteractiveShellRunner` (`@Order(0)`). Runner có thứ tự cao hơn được xem xét trước. Một runner trả về `true` từ `run(String[])` nghĩa là nó đã xử lý lần chạy hiện tại; trả về `false` để runner tiếp theo có cơ hội.

### InteractiveShellRunner

Runner này mở REPL, giữ shell hoạt động để người dùng nhập nhiều lệnh. Những lệnh chỉ có ý nghĩa trong một phiên tương tác, như `exit` hoặc điều khiển lịch sử, thường được thiết kế cho chế độ này.

Trong Spring Shell 3.3.x trở đi, interactive runner không còn được bật mặc định. Cần bật property `spring.shell.interactive.enabled` nếu muốn ứng dụng khởi chạy REPL.

### NonInteractiveShellRunner

Runner này nhận các đối số command từ tiến trình và thực thi command mà không mở prompt. Đây là chế độ phù hợp cho script CI/CD, cron, tác vụ tự động hoặc lời gọi từ một tiến trình khác.

API 3.3.x trở đi có `setCommandsFromArgs(Function<String[], List<String>>)` để tùy chỉnh cách chuyển mảng đối số đầu vào thành một hoặc nhiều chuỗi command. Mỗi chuỗi được mô tả như một command cùng option, ví dụ `history --file myHistory.txt`. Nếu tùy chỉnh cách ánh xạ, cần bảo toàn giá trị có khoảng trắng và quy tắc quoting của parser.

Trong auto-configuration, có thể dùng `NonInteractiveShellRunnerCustomizer` để nhận runner non-interactive được tạo sẵn và cấu hình `setCommandsFromArgs(...)`. Hàm tùy chỉnh nhận `String[]` đối số gốc và trả về `List<String>` gồm zero hoặc nhiều chuỗi command. Hãy dùng extension point này khi ứng dụng cần ánh xạ cú pháp CLI riêng thành command Spring Shell. Nếu phải dựng lại chuỗi command từ token, cần escape theo parser; nối token bằng một dấu cách có thể làm mất ranh giới của giá trị chứa khoảng trắng hoặc dấu nháy.

### ScriptShellRunner

Runner này nhận đối số có tiền tố `@` và xem phần còn lại là đường dẫn file script. Các dòng trong file được đọc và thực thi như command shell; sau khi xử lý script, tiến trình kết thúc.

Ví dụ `deploy.shell`:

```text
connect
login
environment-use staging
resource-use customer-api
deploy
```

Khởi chạy:

```text
java -jar customer-cli.jar @deploy.shell
```

Script runner có độ ưu tiên cao hơn non-interactive runner, do đó đối số `@deploy.shell` được dùng để nhận diện chế độ script khi runner này đã được bật.

## Thay đổi quan trọng từ Spring Shell 3.3.x

API `ShellRunner` đã thay đổi ở mốc 3.3. Điều này quan trọng nếu ứng dụng có custom runner hoặc nâng từ 3.2.x:

| Phiên bản | Hợp đồng chính của `ShellRunner` | Ý nghĩa |
|---|---|---|
| Spring Shell 3.0.x–3.2.x | `canRun(ApplicationArguments)` và `run(ApplicationArguments)` | Runner tự kiểm tra khả năng xử lý rồi thực thi bằng đối tượng Spring Boot |
| Spring Shell 3.3.x–3.4.x | `run(String[] args)` | Runner nhận mảng đối số gốc và trả `boolean` để báo đã xử lý hay chưa |

Từ 3.3.x, phương thức `run(String[])` là API chính. Các phương thức cũ nhận `ApplicationArguments` đã bị deprecated để loại bỏ trong tương lai. Không viết custom runner mới theo cặp `canRun(ApplicationArguments)`/`run(ApplicationArguments)` nếu dự án dùng 3.3.x trở lên.

Ví dụ custom runner cho Spring Shell 3.3.x trở lên:

```java
import org.springframework.core.annotation.Order;
import org.springframework.shell.ShellRunner;
import org.springframework.stereotype.Component;

@Component
@Order(-75)
class BootstrapShellRunner implements ShellRunner {

    @Override
    public boolean run(String[] args) throws Exception {
        if (args.length == 0 || !"bootstrap".equals(args[0])) {
            return false;
        }

        // Xử lý lệnh bootstrap đặc biệt của ứng dụng.
        // Trả true để các ShellRunner sau không nhận cùng lần chạy.
        return true;
    }
}
```

`@Order(-75)` đặt runner này sau script runner (`-100`) nhưng trước non-interactive runner (`-50`). Chỉ dùng thứ tự này nếu ứng dụng thực sự có một kiểu khởi chạy đặc biệt cần được xử lý trước command thông thường. Nếu không, runner mặc định đã đủ.

## Cấu hình runner theo phiên bản

Các property chính:

| Property | Runner được điều khiển |
|---|---|
| `spring.shell.interactive.enabled` | `InteractiveShellRunner` |
| `spring.shell.noninteractive.enabled` | `NonInteractiveShellRunner` |
| `spring.shell.script.enabled` | `ScriptShellRunner` |

Điểm khác biệt mặc định giữa các phiên bản:

- Đến hết dòng 3.2.x: cả ba runner được bật mặc định.
- Từ 3.3.x: chỉ `NonInteractiveShellRunner` được bật mặc định; interactive và script cần bật tường minh.

Ví dụ cấu hình Spring Shell 3.3.x/3.4.x để hỗ trợ cả REPL và script:

```yaml
spring:
  shell:
    interactive:
      enabled: true
    noninteractive:
      enabled: true
    script:
      enabled: true
```

Nếu chỉ muốn ứng dụng chạy command từ đối số tiến trình, có thể giữ cấu hình non-interactive mặc định và không bật hai runner còn lại. Nếu ứng dụng cần prompt, bật `interactive.enabled`. Nếu cần xử lý file `@script`, bật `script.enabled`.

## Phân biệt runner selection và interactionMode của command

`ShellApplicationRunner`/`ShellRunner` quyết định shell sẽ chạy theo cách nào. `InteractionMode` quyết định một command có được xem là phù hợp trong chế độ hiện tại hay không. Hai cơ chế có liên quan nhưng không thay thế nhau.

Trong API legacy annotation của Spring Shell 3.x, `@ShellMethod` có thuộc tính `interactionMode`. Annotation model mới `@Command` trong 3.x cũng hỗ trợ thuộc tính này; điểm khác là `@Command` dùng mảng `InteractionMode[]`, còn `@ShellMethod` dùng một giá trị `InteractionMode`. Các giá trị gồm:

- `InteractionMode.ALL`: command dùng được ở cả hai chế độ; đây là mặc định.
- `InteractionMode.INTERACTIVE`: command chỉ phù hợp với REPL.
- `InteractionMode.NONINTERACTIVE`: command chỉ phù hợp khi chạy command từ đối số hoặc script.

Ví dụ:

```java
import org.springframework.shell.context.InteractionMode;
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;

@ShellComponent
class SessionCommands {

    @ShellMethod(key = "session-exit", interactionMode = InteractionMode.INTERACTIVE)
    public String sessionExit() {
        return "Thoát phiên tương tác.";
    }

    @ShellMethod(key = "health-check", interactionMode = InteractionMode.NONINTERACTIVE)
    public String healthCheck() {
        return "OK";
    }
}
```

`session-exit` chỉ có ý nghĩa khi có phiên REPL cần kết thúc. `health-check` phù hợp với pipeline hoặc script tự động. `interactionMode` là gợi ý khả dụng cho command; nó không tự bật hoặc tắt runner tương ứng.

## Khi nào cần thay ShellApplicationRunner?

Hầu hết ứng dụng nên dùng `DefaultShellApplicationRunner`. Chỉ thay thế khi cần thay đổi chính sách điều phối, chẳng hạn:

- Chọn một runner dựa trên cấu hình riêng của sản phẩm.
- Chuyển đổi đối số khởi động thành một cấu trúc command đặc biệt.
- Chặn hoặc ghi nhận một số kiểu khởi chạy trước khi giao cho runner chuẩn.
- Tích hợp một `ShellRunner` tùy chỉnh với thứ tự ưu tiên riêng.

Ví dụ sau minh họa cách thay runner mặc định trong Spring Shell 3.3.x trở lên. `ShellApplicationRunner` là bean điều phối duy nhất; danh sách `ShellRunner` được Spring sắp xếp theo `@Order`:

```java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.ShellApplicationRunner;
import org.springframework.shell.ShellRunner;

@Configuration
class CustomShellApplicationRunnerConfiguration {

    @Bean
    ShellApplicationRunner shellApplicationRunner(List<ShellRunner> shellRunners) {
        return applicationArguments -> {
            String[] rawArgs = applicationArguments.getSourceArgs();

            for (ShellRunner runner : shellRunners) {
                if (runner.run(rawArgs)) {
                    return;
                }
            }
        };
    }
}
```

Khi có bean tùy chỉnh kiểu `ShellApplicationRunner`, auto-configuration sẽ không tạo runner mặc định. Vì vậy, bean tùy chỉnh phải giữ đầy đủ trách nhiệm dispatch: dùng raw args, duyệt runner theo thứ tự và dừng sau khi một runner trả `true`. Đây là ví dụ cho API 3.3.x trở lên; với 3.0.x–3.2.x, hợp đồng `ShellRunner` vẫn dựa trên `ApplicationArguments`.

Không đăng ký một `ShellApplicationRunner` thứ hai chỉ để log hoặc đọc một option. Với những tác vụ phụ trợ, dùng `ApplicationRunner` riêng để không vô tình thay đổi vòng đời chạy shell.

## Kiểm thử cách chuyển đối số khởi động

Nên kiểm thử riêng việc phân loại của Spring Boot, việc chọn runner và việc thực thi command:

| Trường hợp | Điều cần xác nhận |
|---|---|
| Không có đối số | Runner interactive được bật thì REPL khởi động; nếu không, ứng dụng không tự mở REPL |
| `help` hoặc `version` | Non-interactive runner nhận command và thực thi một lần |
| `deploy --environment=staging` | `getSourceArgs()` giữ cả command lẫn option để shell parser nhận đủ |
| `@deploy.shell` | Script runner nhận file nếu được bật và có độ ưu tiên cao hơn runner khác |
| Option Spring Boot như `--spring.profiles.active=prod` | Boot đọc được property; nếu raw args được chuyển tiếp, custom dispatcher lọc key Boot trước khi gọi runner |
| Custom `ShellRunner` trả `false` | Runner kế tiếp vẫn được thử |
| Custom `ShellRunner` trả `true` | Các runner sau không được gọi cho lần khởi chạy đó |
| `interactionMode` không phù hợp | Command không được cung cấp trong chế độ shell hiện tại |
| Chạy với token có khoảng trắng | Ranh giới token được giữ đúng; không nối mảng args làm mất quoting |

Trong Spring Shell 3.x, `ShellTestClient` có thể tạo phiên interactive hoặc non-interactive để kiểm thử command. Với logic dispatch tùy chỉnh, nên unit test `ShellRunner` bằng các mảng `String[]` đầu vào và xác nhận giá trị boolean, sau đó thêm integration test xác nhận đúng runner được chọn.

## Lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Ứng dụng khởi động xong rồi thoát, không có prompt | Spring Shell 3.3.x trở lên chỉ bật non-interactive runner mặc định | Đặt `spring.shell.interactive.enabled=true` |
| `@script` không chạy | Script runner chưa được bật hoặc file path sai | Bật `spring.shell.script.enabled=true`, kiểm tra đường dẫn và quyền đọc file |
| Command không nhận được option truyền khi khởi động | Dùng `getNonOptionArgs()` để dựng command | Chuyển `getSourceArgs()` cho shell runner |
| Giá trị option bị tách thành token khác | Dựng lại command line bằng cách nối chuỗi mà không xử lý quoting | Giữ raw args hoặc escape theo parser |
| Custom runner không bao giờ được gọi | Runner khác có thứ tự cao hơn đã nhận xử lý | Kiểm tra `@Order` và giá trị boolean trả về |
| Nhiều runner xử lý cùng một lần chạy | Custom runner trả `false` sau khi đã thực thi | Trả `true` ngay khi runner đã nhận trách nhiệm |
| REPL và command một lần có hành vi lẫn nhau | Chưa cấu hình runner hoặc command interaction mode rõ ràng | Cấu hình runner và `InteractionMode` theo mục đích |
| Lỗi biên dịch sau nâng lên 3.3.x | Custom runner vẫn chỉ triển khai API `ApplicationArguments` cũ | Chuyển sang `run(String[])` và trả boolean |
| Có hai vòng chạy shell hoặc hành vi khởi động khó đoán | Đăng ký nhiều bean `ShellApplicationRunner` | Giữ một runner điều phối duy nhất; dùng `ApplicationRunner` cho tác vụ phụ |

## Quy trình xử lý startup arguments

Khi cần nhận đối số lúc khởi động một ứng dụng Spring Shell 3.x, hãy thực hiện theo thứ tự:

1. Xác định phiên bản Spring Shell: 3.0.x–3.2.x hay 3.3.x–3.4.x.
2. Đọc `ApplicationArguments` để phân biệt raw args với option và non-option do Spring Boot phân loại.
3. Giữ `getSourceArgs()` nếu cần chuyển command line nguyên gốc cho shell.
4. Để `DefaultShellApplicationRunner` dispatch tới các `ShellRunner` theo thứ tự, trừ khi có yêu cầu điều phối riêng.
5. Bật runner interactive/script theo property nếu đang dùng 3.3.x trở lên.
6. Dùng `InteractionMode` để giới hạn command theo chế độ chạy.
7. Nếu viết custom `ShellRunner` trong 3.3.x trở lên, dùng `run(String[])` và trả `true` khi đã xử lý.
8. Chỉ thay `ShellApplicationRunner` khi cần thay chính sách dispatch; bảo đảm chỉ có một bean điều phối.
9. Kiểm thử cả command, option, script path và trường hợp runner không nhận xử lý.

Khi giữ đúng raw arguments và phân biệt rõ runner điều phối với runner thực thi, ứng dụng có thể hỗ trợ REPL, command một lần và script mà không làm mất option hoặc khởi chạy sai chế độ.

## Tài liệu tham khảo

- [Spring Shell 3.3.4 — Execution](https://docs.spring.io/spring-shell/reference/3.3/execution.html): `ShellApplicationRunner`, ba `ShellRunner`, property bật/tắt và thay đổi API từ 3.3.x.
- [Spring Shell 3.3.0 API — DefaultShellApplicationRunner](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/DefaultShellApplicationRunner.html): runner mặc định điều phối danh sách `ShellRunner`.
- [Spring Shell 3.4.x API — NonInteractiveShellRunner](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/jline/NonInteractiveShellRunner.html): chạy command từ raw arguments và tùy chỉnh `setCommandsFromArgs`.
- [Spring Shell 3.4.x API — ScriptShellRunner](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/jline/ScriptShellRunner.html): nhận đối số `@file` để chạy script.
- [Spring Shell 3.4.x API — ShellRunner](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/ShellRunner.html): API `run(String[])` từ 3.3.x và các phương thức cũ nhận `ApplicationArguments` bị deprecated.
- [Spring Shell 3.4.x API — NonInteractiveShellRunnerCustomizer](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/boot/NonInteractiveShellRunnerCustomizer.html): extension point tùy chỉnh runner non-interactive.
- [Spring Shell 3.4.x API — InteractionMode](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/context/InteractionMode.html): các chế độ ALL, INTERACTIVE và NONINTERACTIVE.
- [Spring Boot 3.4 — Accessing Application Arguments](https://docs.spring.io/spring-boot/3.4/reference/features/spring-application.html): `ApplicationArguments`, source args, option names/values và non-option args.
