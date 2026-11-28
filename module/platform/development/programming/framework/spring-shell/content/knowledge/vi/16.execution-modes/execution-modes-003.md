# InteractiveShellRunner, NonInteractiveShellRunner và ScriptShellRunner ở 3.x

Spring Shell 3.x có thể chạy command theo ba cách: mở một phiên shell tương tác, nhận command trực tiếp từ đối số khởi động hoặc đọc một file script rồi thực thi các lệnh trong file. Ba cách chạy này được triển khai bởi **InteractiveShellRunner**, **NonInteractiveShellRunner** và **ScriptShellRunner**.

Các runner cùng thực thi command thông qua shell và registry hiện tại, nhưng khác nhau ở nguồn input và vòng đời tiến trình. Interactive runner giữ phiên làm việc để người dùng nhập tiếp; non-interactive runner xử lý command được truyền lúc khởi động rồi kết thúc; script runner lấy danh sách lệnh từ file rồi thoát khi hoàn tất.

Một thay đổi cần chú ý khi nâng từ Spring Shell 3.2 lên 3.3: trước 3.3, cả ba runner được bật mặc định; từ 3.3.x, chỉ **NonInteractiveShellRunner** được bật mặc định. Vì vậy, ứng dụng 3.3 cần bật rõ interactive hoặc script runner nếu muốn dùng các chế độ đó.

## 1. Ba runner giải quyết ba cách sử dụng

| Runner | Nguồn lệnh | Vòng đời | Trường hợp sử dụng |
|---|---|---|---|
| **InteractiveShellRunner** | Người dùng nhập tại prompt | Chạy vòng lặp cho đến khi thoát hoặc input kết thúc | CLI dành cho người vận hành, khám phá lệnh và thao tác nhiều bước |
| **NonInteractiveShellRunner** | Đối số của tiến trình khi khởi động | Thực thi command rồi kết thúc | Chạy một thao tác từ terminal, CI hoặc automation |
| **ScriptShellRunner** | File được chỉ định bằng đối số bắt đầu bằng ký tự @ | Đọc và chạy script rồi kết thúc | Chạy một chuỗi thao tác đã chuẩn bị sẵn |

Ba runner đều triển khai interface **ShellRunner**. Trong Spring Boot, **ShellApplicationRunner** nhận các đối số khởi động và điều phối runner phù hợp. Mặc định, ứng dụng sử dụng **DefaultShellApplicationRunner** để gọi runner theo thứ tự ưu tiên và chọn runner có thể xử lý đầu vào hiện tại.

~~~mermaid
flowchart TD
    A["Spring Boot khởi động ứng dụng"] --> B["ShellApplicationRunner"]
    B --> C["Danh sách ShellRunner theo thứ tự ưu tiên"]
    C --> D{"Có đối số @file?"}
    D -->|Có| E["ScriptShellRunner"]
    D -->|Không| F{"Có command đầu vào?"}
    F -->|Có| G["NonInteractiveShellRunner"]
    F -->|Không| H["InteractiveShellRunner"]
    E --> I["Đọc và thực thi script"]
    G --> J["Thực thi command từ args"]
    H --> K["Mở prompt và vòng lặp REPL"]
    I --> L["Kết thúc tiến trình"]
    J --> L
    K --> M["Người dùng nhập lệnh tiếp"]
    M --> K
~~~

Sơ đồ mô tả luồng thường gặp khi các runner tương ứng đã được bật. Runner thực tế được chọn dựa trên khả năng xử lý đối số và thứ tự ưu tiên, không phải do command method tự quyết định.

## 2. InteractiveShellRunner: chạy phiên REPL

**InteractiveShellRunner** khởi tạo shell tương tác. Người dùng nhìn thấy prompt, nhập command, nhận kết quả rồi tiếp tục nhập lệnh khác trong cùng tiến trình.

Trong Spring Shell 3.x, runner này nằm trong package **org.springframework.shell.jline** và dùng JLine để đọc dòng lệnh. JLine cung cấp trải nghiệm terminal như lịch sử lệnh, chỉnh sửa dòng và hoàn thành lệnh bằng phím Tab khi các thành phần tương ứng được cấu hình.

Một phiên làm việc có thể trông như sau:

~~~text
$ ./my-shell

my-shell:> help
AVAILABLE COMMANDS
...

my-shell:> project list
...

my-shell:> project status --id=42
...

my-shell:> exit
~~~

Command được chạy nhiều lần mà không phải khởi động lại ứng dụng. Đây là chế độ phù hợp khi người dùng cần khám phá command, thực hiện nhiều bước liên tiếp hoặc cần prompt hỏi thêm dữ liệu.

### 2.1. Bật interactive runner trong Spring Shell 3.3

Từ Spring Shell 3.3, **InteractiveShellRunner** không còn được bật mặc định. Bật nó bằng thuộc tính:

~~~yaml
spring:
  shell:
    interactive:
      enabled: true
~~~

Nếu dùng Spring Shell 3.2.x hoặc cũ hơn, cả ba runner được bật mặc định theo cấu hình tiêu chuẩn. Khi nâng lên 3.3.x, nếu ứng dụng đột nhiên không còn hiển thị prompt, hãy kiểm tra thuộc tính **spring.shell.interactive.enabled** trước khi điều tra command registration.

### 2.2. Khi nào không nên chọn interactive?

Interactive runner cần một nguồn input tương tác. Nó không phải lựa chọn phù hợp cho tác vụ được gọi từ pipeline hoặc CI mà không có người nhập câu trả lời. Nếu command cần chạy tự động, hãy truyền option/argument đầy đủ và dùng non-interactive runner hoặc script runner.

Một command có thể yêu cầu xác nhận hoặc hỏi thêm dữ liệu khi chạy trong phiên tương tác. Với tác vụ tự động, hãy thiết kế option rõ ràng để người gọi truyền quyết định thay vì chờ prompt.

## 3. NonInteractiveShellRunner: chạy command từ đối số khởi động

**NonInteractiveShellRunner** thực thi command được truyền vào khi khởi chạy ứng dụng mà không mở vòng lặp prompt. Khi command hoàn tất, ứng dụng kết thúc.

Ví dụ:

~~~text
$ ./my-shell help
$ ./my-shell project-list
$ ./my-shell project-create --name=demo
~~~

Runner lấy đối số tiến trình và chuyển chúng thành một hoặc nhiều command cần thực thi. API của runner cũng cho phép tùy chỉnh cách ánh xạ đối số thành danh sách command bằng hàm **setCommandsFromArgs(...)**. Parser được dùng để phân tích chuỗi command trước khi shell thực thi.

Trong Spring Shell 3.3.x, **NonInteractiveShellRunner** là runner duy nhất được bật mặc định. Thuộc tính cấu hình tương ứng là **spring.shell.noninteractive.enabled**:

~~~yaml
spring:
  shell:
    noninteractive:
      enabled: true
~~~

Giá trị mặc định của thuộc tính này là bật trong cấu hình auto-configuration 3.3.x. Có thể đặt rõ **true** trong file cấu hình để thể hiện ý định của ứng dụng.

### 3.1. Chạy command từ script CI

Một bước CI có thể gọi ứng dụng trực tiếp:

~~~text
./my-shell project-deploy --environment=staging --version=1.8.2
~~~

Ứng dụng nhận command cùng option, thực thi và kết thúc. Không cần giữ một terminal mở để chờ người vận hành nhập lệnh tiếp theo.

Với non-interactive mode, command nên nhận đủ dữ liệu qua option hoặc argument. Không nên phụ thuộc vào prompt, thao tác bàn phím hoặc trạng thái chỉ tồn tại trong phiên REPL trước đó.

## 4. ScriptShellRunner: chạy file script khi khởi động

**ScriptShellRunner** tìm đối số tiến trình bắt đầu bằng ký tự **@**. Phần sau ký tự đó được xem là đường dẫn đến file script. Runner đọc file, thực thi các command trong đó rồi kết thúc ứng dụng.

Ví dụ:

~~~text
$ ./my-shell @./scripts/prepare-environment.shell
~~~

File **prepare-environment.shell** có thể chứa các command:

~~~text
project status --id=42
environment select --name=staging
project deploy --id=42
project verify --id=42
~~~

Script runner hữu ích khi một quy trình gồm nhiều command theo thứ tự cố định. Người vận hành có thể lưu quy trình trong file, đưa file vào version control và chạy lại khi cần.

### 4.1. Bật ScriptShellRunner

Trong Spring Shell 3.3.x, script runner không được bật mặc định. Bật bằng:

~~~yaml
spring:
  shell:
    script:
      enabled: true
~~~

Nếu ứng dụng cần cả REPL lẫn script khi khởi động, có thể bật cả hai:

~~~yaml
spring:
  shell:
    interactive:
      enabled: true
    noninteractive:
      enabled: true
    script:
      enabled: true
~~~

Trong cấu hình trên, non-interactive vẫn được bật tường minh để dễ đọc; ở Spring Shell 3.3.x nó vốn đã là runner mặc định. Khi nhiều runner cùng bật, cơ chế điều phối và thứ tự ưu tiên sẽ quyết định runner nào xử lý đối số.

### 4.2. ScriptShellRunner khác command script tích hợp

Cần phân biệt hai cách chạy file:

- **ScriptShellRunner** hoạt động lúc khởi động ứng dụng. Nó nhận đối số dạng **@file**, chạy script rồi kết thúc.
- Command tích hợp **script** được gọi từ một shell đang chạy. Người dùng nhập command script để đọc file và thực thi các lệnh trong file ngay trong phiên hiện tại.

Ví dụ về cách gọi command tích hợp trong shell:

Khi đang ở prompt, dùng **help script** để xem cú pháp chính xác của command script theo phiên bản đang chạy. Command này hữu ích khi người dùng đã mở REPL và muốn chạy một chuỗi thao tác mà không thoát phiên. ScriptShellRunner phù hợp khi file script chính là đầu vào lúc khởi động.

Tài liệu Spring Shell 3.3 mô tả file của built-in script command có cách đọc giống input trong interactive shell: dòng bắt đầu bằng **//** là comment và dòng kết thúc bằng dấu gạch chéo ngược có thể nối tiếp sang dòng kế tiếp. Nhờ vậy, một command dài có thể được trình bày trên nhiều dòng trong file.

~~~text
// Kiểm tra trước khi triển khai
project status --id=42
project deploy --id=42 --environment=staging
~~~

File script nên được kiểm tra trước khi chạy: đường dẫn tồn tại, nội dung đúng cú pháp và các option cần thiết đã có. Không đặt mật khẩu hoặc token thật trong file script được chia sẻ hoặc đưa vào repository; dùng cơ chế secret của môi trường chạy.

## 5. Thứ tự ưu tiên của các runner

Các runner được sắp xếp theo thứ tự ưu tiên. Trong API JLine 3.x, thứ tự thường gặp là:

| Runner | Giá trị @Order | Ý nghĩa |
|---|---:|---|
| **ScriptShellRunner** | -100 | Được hỏi trước; xử lý đối số dạng @file |
| **NonInteractiveShellRunner** | -50 | Xử lý command từ đối số tiến trình |
| **InteractiveShellRunner** | 0 | Mở REPL khi runner ưu tiên cao hơn không nhận xử lý |

**DefaultShellApplicationRunner** điều phối danh sách runner theo thứ tự và chuyển cho runner đầu tiên có thể xử lý shell. Do đó, nếu script runner và non-interactive runner cùng được bật, đối số **@file** được script runner ưu tiên xử lý trước.

Không nên dựa vào việc một runner đã được bật để kết luận nó chắc chắn sẽ chạy. Cần kiểm tra cả đối số khởi động, thứ tự ưu tiên và điều kiện runner có thể xử lý input hiện tại.

## 6. Bật/tắt runner theo từng môi trường

Có thể dùng Spring profile để cấu hình chế độ chạy khác nhau giữa máy phát triển và môi trường tự động hóa.

Ví dụ file **application-dev.yml** bật interactive:

~~~yaml
spring:
  shell:
    interactive:
      enabled: true
    noninteractive:
      enabled: true
    script:
      enabled: false
~~~

File **application-ci.yml** bật non-interactive và script:

~~~yaml
spring:
  shell:
    interactive:
      enabled: false
    noninteractive:
      enabled: true
    script:
      enabled: true
~~~

Chạy ứng dụng với profile phù hợp:

~~~text
./my-shell --spring.profiles.active=dev
./my-shell --spring.profiles.active=ci @./scripts/ci-checks.shell
~~~

Hãy kiểm tra cách truyền đối số của launcher và môi trường triển khai. Những option thuộc Spring Boot như profile cần được nhận diện đúng như cấu hình ứng dụng; command token của Spring Shell phải được chuyển đến runner tương ứng.

## 7. InteractionMode: giới hạn command theo chế độ shell

Runner quyết định cách shell nhận input và chạy. **InteractionMode** lại quyết định command nào được xem là phù hợp với chế độ hiện tại.

Spring Shell 3.x có ba giá trị:

| Giá trị | Ý nghĩa |
|---|---|
| **ALL** | Command khả dụng trong cả hai chế độ |
| **INTERACTIVE** | Command chỉ phù hợp với phiên tương tác |
| **NONINTERACTIVE** | Command chỉ phù hợp khi chạy không tương tác |

Mặc định, command có **InteractionMode.ALL**. Có thể đặt chế độ trong annotation **@ShellMethod**:

~~~java
import org.springframework.shell.context.InteractionMode;
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;

@ShellComponent
class ModeSpecificCommands {

    @ShellMethod(
            key = "choose-from-menu",
            value = "Mở menu để chọn thao tác.",
            interactionMode = InteractionMode.INTERACTIVE
    )
    public String chooseFromMenu() {
        return "Đang mở menu tương tác";
    }

    @ShellMethod(
            key = "import-batch",
            value = "Nhập dữ liệu theo lô.",
            interactionMode = InteractionMode.NONINTERACTIVE
    )
    public String importBatch() {
        return "Đã nhận yêu cầu nhập dữ liệu";
    }
}
~~~

Với mô hình đăng ký bằng mã, có thể cấu hình tương tự qua **CommandRegistration.Builder**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.command.CommandRegistration;
import org.springframework.shell.context.InteractionMode;

@Configuration
class ImportBatchCommandConfiguration {

    @Bean
    CommandRegistration importBatchCommand() {
        return CommandRegistration.builder()
                .command("import-batch")
                .interactionMode(InteractionMode.NONINTERACTIVE)
                .build();
    }
}
~~~

InteractionMode là metadata về khả năng sử dụng command, không phải công tắc bật/tắt runner. Ví dụ, đặt command thành **INTERACTIVE** không tự bật **InteractiveShellRunner**. Ứng dụng vẫn cần cấu hình runner phù hợp.

## 8. ShellRunner và ShellApplicationRunner trong 3.3

**ShellRunner** là hợp đồng chung cho các runner. **ShellApplicationRunner** là thành phần tích hợp với vòng đời Spring Boot và chọn runner để thực thi.

Spring Shell 3.3 bổ sung phương thức:

~~~java
default boolean run(String[] args) throws Exception {
    return false;
}
~~~

Phương thức nhận raw arguments của tiến trình. Giá trị trả về cho biết runner đã xử lý lần chạy hay chưa:

- Trả về **true** khi runner đã thực hiện và không cần runner tiếp theo.
- Trả về **false** khi runner không xử lý input hiện tại để bộ điều phối có thể thử runner tiếp theo.

Các phương thức cũ nhận **ApplicationArguments**, gồm **canRun(ApplicationArguments)** và **run(ApplicationArguments)**, bị deprecated từ 3.3.0 và được đánh dấu sẽ bị loại bỏ. Khi tự triển khai **ShellRunner**, nên dùng **run(String[])**.

**DefaultShellApplicationRunner** là implementation mặc định. Nó nhận danh sách **ShellRunner** và điều phối runner đầu tiên có thể xử lý shell. Một application context chỉ nên có một **ShellApplicationRunner**; chỉ thay thế nó khi ứng dụng thật sự cần quy tắc điều phối riêng.

Không cần tự tạo runner cho những trường hợp thông thường. Ba runner có sẵn đáp ứng các nhu cầu REPL, chạy một command và chạy script. Tùy biến chỉ nên được cân nhắc khi ứng dụng cần nguồn input, cách phân tích đối số hoặc quy tắc dispatch khác.

## 9. Chọn chế độ phù hợp

| Tình huống | Runner nên dùng | Lý do |
|---|---|---|
| Người vận hành mở terminal và nhập nhiều lệnh | InteractiveShellRunner | Giữ phiên làm việc và prompt |
| CI gọi một command rồi lấy kết quả | NonInteractiveShellRunner | Không cần prompt và kết thúc sau command |
| Một quy trình có nhiều command cố định | ScriptShellRunner | Đọc các lệnh theo thứ tự từ file |
| Muốn chạy script trong một phiên REPL đang mở | Built-in script command | Không cần khởi động lại ứng dụng |
| Command mở menu hoặc hỏi người dùng | Interactive mode và InteractionMode.INTERACTIVE | Cần input từ người vận hành |
| Command nhập dữ liệu theo batch | Non-interactive mode và InteractionMode.NONINTERACTIVE | Có thể truyền đầy đủ option/argument |

Một CLI có thể hỗ trợ cả người vận hành lẫn automation. Hãy giữ logic nghiệp vụ trong service dùng chung, còn command chỉ chuyển input sang service và trình bày kết quả. Khi đó, cùng một nghiệp vụ có thể được gọi từ REPL, command trực tiếp hoặc script mà không phải sao chép logic.

## 10. Lỗi thường gặp khi cấu hình execution mode

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Ứng dụng 3.3 khởi động rồi kết thúc, không có prompt | InteractiveShellRunner chưa được bật | Đặt **spring.shell.interactive.enabled=true** |
| Đối số @file không chạy | ScriptShellRunner chưa được bật hoặc đường dẫn sai | Bật **spring.shell.script.enabled** và kiểm tra file |
| Command chạy rồi ứng dụng thoát ngay | Đang dùng NonInteractiveShellRunner | Bật interactive nếu cần giữ phiên |
| Command tương tác không xuất hiện trong non-interactive mode | Command giới hạn bằng InteractionMode.INTERACTIVE | Đổi mode nếu command thực sự hỗ trợ cả hai |
| Command không phù hợp vẫn xuất hiện ở chế độ khác | Metadata InteractionMode chưa được khai báo đúng | Đặt ALL, INTERACTIVE hoặc NONINTERACTIVE theo hành vi |
| Script bị xử lý như command thông thường | Đối số không bắt đầu bằng @ hoặc script runner không được bật | Kiểm tra cú pháp đối số và thuộc tính script |
| Runner tùy chỉnh không được gọi | Runner ưu tiên cao hơn đã nhận xử lý đối số | Kiểm tra thứ tự và giá trị trả về của run(String[]) |
| Code mới còn dùng run(ApplicationArguments) | Chưa cập nhật API từ 3.3 | Chuyển sang run(String[]) |
| Lệnh exit không có ý nghĩa khi chạy tự động | Exit được thiết kế để kết thúc phiên REPL | Chỉ dùng exit trong interactive mode |

## 11. Kiểm thử các chế độ thực thi

Không nên chỉ kiểm tra command method. Cần kiểm thử cả cách ứng dụng chọn runner:

1. **Interactive:** bật interactive runner, khởi động shell, gửi nhiều command trong cùng phiên và xác nhận phiên chỉ kết thúc khi có yêu cầu thoát.
2. **Non-interactive:** truyền một command qua đối số khởi động, xác nhận command được thực thi và tiến trình kết thúc.
3. **Script:** bật script runner, truyền đối số @file, xác nhận các command trong file được thực thi theo thứ tự.
4. **Runner disabled:** tắt một runner, xác nhận chế độ tương ứng không được chọn.
5. **InteractionMode:** xác nhận command chỉ dành cho interactive không xuất hiện/khả dụng trong non-interactive và ngược lại.
6. **Ưu tiên:** khi nhiều runner cùng bật, xác nhận @file được script runner xử lý trước.
7. **Sai input:** kiểm tra file không tồn tại, command sai cú pháp và option thiếu.
8. **Exit code:** xác nhận mã thoát phản ánh thành công hoặc thất bại theo thiết kế của ứng dụng.
9. **Spring profiles:** xác nhận cấu hình dev và CI bật đúng runner.
10. **ShellRunner tùy chỉnh:** nếu có, xác nhận run(String[]) trả về true khi đã xử lý và false khi nhường cho runner sau.

Spring Shell cung cấp **ShellTestClient** để kiểm thử các phiên interactive và non-interactive. Với script runner, nên có kiểm thử tích hợp ở cấp khởi động ứng dụng để xác nhận đối số @file thực sự được nhận diện và file được thực thi.

## 12. Khác biệt cần nhớ giữa Spring Shell 3.2 và 3.3

| Nội dung | Spring Shell đến 3.2.x | Spring Shell 3.3.x |
|---|---|---|
| Runner mặc định | Cả ba runner được bật theo cấu hình tiêu chuẩn | Chỉ NonInteractiveShellRunner bật mặc định |
| Interactive REPL | Có thể chạy ngay với cấu hình mặc định | Cần bật **spring.shell.interactive.enabled=true** |
| Script startup runner | Được bật mặc định | Cần bật **spring.shell.script.enabled=true** |
| Non-interactive runner | Được bật mặc định | Vẫn bật mặc định |
| ShellRunner API | Dùng các phương thức nhận ApplicationArguments | Có **run(String[])**; API ApplicationArguments bị deprecated |

Khi nâng từ 3.2.x lên 3.3.x, hãy rà soát cấu hình runner trước khi kiểm tra các command. Ứng dụng trước đây tự mở prompt có thể chuyển sang chỉ chạy non-interactive vì interactive runner không còn được bật mặc định.

## Tài liệu tham khảo

- [Spring Shell 3.3.4 — Execution](https://docs.spring.io/spring-shell/reference/3.3/execution.html) — ba runner, cấu hình bật/tắt và thay đổi từ 3.2 sang 3.3.
- [Spring Shell 3.3.4 — Built-in Script Command](https://docs.spring.io/spring-shell/reference/3.3/commands/builtin/script.html) — đọc và chạy file script trong phiên shell, comment và line continuation.
- [Spring Shell 3.3.0 API — InteractiveShellRunner](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/jline/InteractiveShellRunner.html) — runner mở phiên shell tương tác.
- [Spring Shell 3.3.0 API — NonInteractiveShellRunner](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/jline/NonInteractiveShellRunner.html) — thực thi command từ đối số tiến trình và tùy chỉnh ánh xạ args.
- [Spring Shell 3.3.0 API — ScriptShellRunner](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/jline/ScriptShellRunner.html) — nhận đối số bắt đầu bằng @ để chạy file script.
- [Spring Shell 3.3.0 API — ShellRunner](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/ShellRunner.html) — hợp đồng run(String[]) và các phương thức ApplicationArguments deprecated.
- [Spring Shell 3.3.0 API — DefaultShellApplicationRunner](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/DefaultShellApplicationRunner.html) — điều phối runner đầu tiên có thể xử lý shell.
- [Spring Shell 3.3.4 — Interaction Mode](https://spring-shell.spring-doc.cn/docs/3.3.4/commands_interactionmode.en.html) — giới hạn command theo ALL, INTERACTIVE và NONINTERACTIVE.
- [Spring Shell 3.3.4 — Getting Started](https://docs.spring.io/spring-shell/reference/3.3/getting-started.html) — ví dụ chạy ứng dụng ở interactive và non-interactive mode.
