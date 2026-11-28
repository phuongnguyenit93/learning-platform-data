# Chọn một runner thực thi và chế độ ngay khi khởi động ở 4.x

Spring Shell 4.x yêu cầu ứng dụng chọn cách chạy shell ngay từ lúc khởi động. Ứng dụng có thể mở một phiên tương tác để người dùng nhập nhiều command, hoặc chạy command được truyền qua process arguments rồi kết thúc. Lớp thực hiện vòng đời đó là **ShellRunner**.

Spring Shell 4.x có ba runner tích hợp: **SystemShellRunner**, **JLineShellRunner** và **NonInteractiveShellRunner**. Ứng dụng chỉ sử dụng một runner cho mỗi ApplicationContext. Thuộc tính **spring.shell.interactive.enabled** quyết định chọn nhóm interactive hay non-interactive; sự hiện diện của JLine quyết định runner interactive dùng Console chuẩn hay JLine.

Điểm cần nhớ khi nâng cấp từ 3.x là Spring Shell 4.x không tự chuyển sang non-interactive chỉ vì process nhận command-line arguments. Interactive mode được bật mặc định. Nếu muốn chạy một command rồi thoát, phải tắt interactive mode trước khi runner khởi động.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vai trò của ShellRunner trong vòng đời ứng dụng Spring Shell 4.x.
- Phân biệt SystemShellRunner, JLineShellRunner và NonInteractiveShellRunner.
- Chọn interactive hoặc non-interactive mode bằng cấu hình trước khi khởi động.
- Hiểu cách Spring Boot tự gọi runner qua ApplicationRunner.
- Chạy một command từ process arguments và chạy một file script.
- Phân biệt command script --file với runner riêng biệt.
- Nhận biết những thay đổi về runner và InteractionMode khi chuyển từ Spring Shell 3.x sang 4.x.
- Kiểm thử đúng runner, chế độ, command arguments và script theo môi trường triển khai.

## 1. Runner là thành phần nào?

ShellRunner là abstraction chịu trách nhiệm đưa shell vào hoạt động. Nó nhận mảng chuỗi arguments, đọc input hoặc phân tích command, chuyển lệnh tới command registry và điều khiển vòng đời thực thi tương ứng.

Trong Spring Shell 4.x, interface có phương thức chính:

    public interface ShellRunner {
        void run(String[] args) throws Exception;
    }

args là các đối số thô mà runner nhận được từ lúc ứng dụng khởi động. Runner interactive dùng input provider để đọc nhiều dòng từ người dùng. Runner non-interactive phân tích command từ arguments, thực thi rồi kết thúc.

Có thể hình dung luồng khởi động như sau:

    flowchart TD
        A[Ứng dụng bắt đầu khởi động] --> B[Đọc cấu hình Spring Shell]
        B --> C{spring.shell.interactive.enabled?}
        C -->|true hoặc không khai báo| D{Có JLine trên classpath?}
        D -->|Có| E[JLineShellRunner]
        D -->|Không| F[SystemShellRunner]
        C -->|false| G[NonInteractiveShellRunner]
        E --> H[ShellRunner.run args]
        F --> H
        G --> H
        H --> I[Nhận input hoặc thực thi command]

Runner được chọn trong quá trình tạo ApplicationContext. Việc thay đổi property sau khi shell đã bắt đầu chạy không phải cách chuyển một phiên đang hoạt động từ interactive sang non-interactive.

## 2. Ba runner tích hợp trong Spring Shell 4.x

| Runner | Cách nhận input | Trường hợp sử dụng |
|---|---|---|
| SystemShellRunner | Java System.console() | Phiên tương tác cơ bản, không cần JLine |
| JLineShellRunner | JLine input provider | Phiên tương tác cần lịch sử, completion và tính năng terminal nâng cao |
| NonInteractiveShellRunner | Process arguments hoặc script | Chạy một command, automation, batch và pipeline |

### 2.1. SystemShellRunner

SystemShellRunner là interactive runner dựa trên java.io.Console. Nó thuộc module core và không cần dependency JLine.

Runner này phù hợp khi ứng dụng cần prompt cơ bản và muốn giữ dependency nhỏ. Nó cung cấp vòng lặp nhập command và hiển thị kết quả, nhưng không có các tính năng nâng cao của JLine như lịch sử lệnh, tab completion và định dạng terminal phong phú.

Spring Shell 4.x dùng SystemShellRunner khi interactive mode được bật nhưng cấu hình JLine không có trên classpath. Đây cũng là lựa chọn mặc định trong một số cách khởi tạo thuần Spring context không dùng starter Boot.

### 2.2. JLineShellRunner

JLineShellRunner là interactive runner dùng JLine để đọc và xử lý input. Đây là lựa chọn phù hợp cho CLI tương tác thường xuyên, cần lịch sử command, completion, highlighter và khả năng làm việc với terminal phong phú hơn.

Spring Shell 4.x tách JLine khỏi core. Module spring-shell-core không tự kéo JLine theo dependency. Nếu muốn dùng JLine, cần có spring-shell-jline trên classpath hoặc dùng starter đã đưa module này vào dependency graph.

Khi interactive mode được bật và cấu hình JLine được nạp, Spring Shell tạo JLineShellRunner. Nếu ứng dụng không có JLine, runner interactive chuyển về SystemShellRunner.

### 2.3. NonInteractiveShellRunner

NonInteractiveShellRunner chạy command mà không mở prompt để chờ người dùng nhập thêm. Nó phù hợp với:

- Command được gọi từ script hệ điều hành.
- Tác vụ batch hoặc lịch chạy tự động.
- CI/CD pipeline.
- Công cụ cần nhận arguments, xuất kết quả và kết thúc process.
- Chạy chuỗi command từ file script.

Ví dụ, một công cụ quản trị có thể được gọi để xuất báo cáo:

    java -Dspring.shell.interactive.enabled=false -jar support-cli.jar report export --format csv --output reports/daily.csv

Ứng dụng khởi động, chạy command report export với các option đã truyền, sau đó kết thúc thay vì hiển thị prompt.

API của NonInteractiveShellRunner cũng hỗ trợ truyền script file bằng cách đặt ký tự @ trước tên file trong mảng arguments. Ngoài cơ chế cấp runner này, Spring Shell còn có command tích hợp script --file để đọc và thực thi file; hai cách này không phải hai runner riêng biệt.

## 3. Chọn chế độ bằng spring.shell.interactive.enabled

Trong Spring Shell 4.x, thuộc tính chính để chọn chế độ là:

    spring.shell.interactive.enabled

| Giá trị | Runner được chọn | Hành vi |
|---|---|---|
| true | JLineShellRunner nếu JLine có mặt; nếu không là SystemShellRunner | Mở phiên tương tác và tiếp tục chờ input |
| false | NonInteractiveShellRunner | Chạy command hoặc script từ arguments rồi kết thúc |
| Không khai báo | Mặc định là true | Chạy interactive mode |

Có thể cấu hình trong application.yml:

    spring:
      shell:
        interactive:
          enabled: true

Đây là cấu hình phù hợp cho ứng dụng thường được mở như một REPL. Người dùng chạy JAR và tiếp tục nhập command tại prompt.

Để chạy command từ process arguments, đặt:

    spring:
      shell:
        interactive:
          enabled: false

Khi đó Spring Shell chọn NonInteractiveShellRunner.

**Lưu ý:** trong Spring Shell 4.x, interactive mode vẫn bật mặc định ngay cả khi process nhận arguments. Không dựa vào việc có arguments để suy ra runner sẽ tự chuyển sang non-interactive.

## 4. Chọn chế độ theo môi trường triển khai

Một ứng dụng có thể cần interactive mode khi chạy trên máy phát triển, nhưng cần non-interactive mode khi chạy trong CI hoặc lịch batch. Có thể tách cấu hình theo Spring profile.

Ví dụ file application.yml cho môi trường sử dụng thông thường:

    spring:
      shell:
        interactive:
          enabled: true

File application-batch.yml:

    spring:
      shell:
        interactive:
          enabled: false

Khởi chạy batch profile:

    java -Dspring.profiles.active=batch -jar support-cli.jar report export --format csv --output reports/daily.csv

Spring Boot nạp application-batch.yml, đặt interactive thành false, rồi tạo runner non-interactive cho lần khởi động đó.

Có thể dùng biến môi trường thay cho profile:

    SPRING_SHELL_INTERACTIVE_ENABLED=false java -jar support-cli.jar report export --format csv

Trong PowerShell:

    $env:SPRING_SHELL_INTERACTIVE_ENABLED = 'false'
    java -jar support-cli.jar report export --format csv

Hoặc dùng Java system property đặt trước -jar:

    java -Dspring.shell.interactive.enabled=false -jar support-cli.jar report export --format csv

Đặt cấu hình trước khi process khởi tạo ApplicationContext để auto-configuration chọn đúng runner.

## 5. Chạy interactive mode

Khi interactive mode được bật, ứng dụng mở prompt và chờ người dùng nhập command. Ví dụ:

    java -jar support-cli.jar

Prompt minh họa:

    support:> help
    support:> customer list
    support:> report export --format csv
    support:> quit

Trong phiên này, runner tiếp tục tồn tại sau khi một command hoàn tất. Người dùng có thể chạy command tiếp theo mà không phải khởi động lại JVM.

Nếu có JLine trên classpath, phiên tương tác có thể sử dụng lịch sử, completion và tính năng terminal do JLine cung cấp. Nếu không có JLine, SystemShellRunner cung cấp vòng lặp tương tác cơ bản.

### 5.1. Có arguments không có nghĩa là non-interactive

Một điểm dễ gây nhầm lẫn khi nâng cấp là lệnh:

    java -jar support-cli.jar customer list --limit 20

Trong Spring Shell 4.x, nếu spring.shell.interactive.enabled vẫn là true, ứng dụng vẫn được khởi tạo ở interactive mode. Không coi dòng trên là cách bảo đảm chạy một command rồi thoát. Muốn thực thi command từ arguments, phải đặt interactive thành false trước khi khởi động.

## 6. Chạy một command trong non-interactive mode

Khi tắt interactive, runner đọc command và option từ process arguments. Ví dụ:

    java -Dspring.shell.interactive.enabled=false -jar support-cli.jar customer list --limit 20

Hoặc trên Windows:

    java -Dspring.shell.interactive.enabled=false -jar support-cli.jar customer list --limit 20

Command được thực thi mà không mở prompt. Cách chạy này phù hợp để gọi từ PowerShell, Bash, scheduler hoặc pipeline.

Một command non-interactive nên có input đầy đủ qua arguments, option hoặc cấu hình. Không nên thiết kế luồng nghiệp vụ bắt buộc chờ người dùng nhập thêm dữ liệu nếu command được dùng trong automation.

### 6.1. Dùng arguments và option rõ ràng

Ví dụ command:

    customer find --customer-id C-100 --include-disabled false

Có thể chạy bằng:

    java -Dspring.shell.interactive.enabled=false -jar support-cli.jar customer find --customer-id C-100 --include-disabled false

Hãy dùng cú pháp option đã được command khai báo. Process arguments đi qua command parser của Spring Shell; chúng không phải câu lệnh shell tùy ý của hệ điều hành.

### 6.2. Cấu hình ở đúng lớp

Có hai nhóm đối số thường bị nhầm:

- JVM options như -Dspring.shell.interactive.enabled=false được đặt trước -jar.
- Arguments của ứng dụng như customer list --limit 20 được đặt sau tên JAR.

Ví dụ:

    java -Dspring.shell.interactive.enabled=false -jar support-cli.jar customer list --limit 20

Nếu đặt -D... sau -jar, Java launcher sẽ xem nó là argument của ứng dụng thay vì system property của JVM. Vì vậy, hãy đặt JVM option trước -jar.

## 7. Chạy nhiều command từ file script

Spring Shell 4.x cung cấp command tích hợp script để đọc và thực thi một chuỗi command từ file. Mỗi dòng chứa một command; các dòng được thực thi theo thứ tự xuất hiện. Có thể thêm comment bằng cách bắt đầu dòng với //.

Ví dụ file daily-report.shell:

    // Chọn môi trường làm việc
    environment select staging
    customer list --limit 100
    report export --format csv --output reports/daily.csv

Command script nhận đường dẫn file qua option --file. Đường dẫn có thể là đường dẫn filesystem tuyệt đối hoặc Spring resource reference:

    script --file /absolute/path/daily-report.shell
    script --file file:/absolute/path/daily-report.shell
    script --file classpath:scripts/daily-report.shell

Trong phiên interactive, nhập:

    support:> script --file file:/opt/jobs/daily-report.shell

Spring Shell đọc file và chạy các command theo thứ tự. Người dùng có thể tiếp tục phiên tương tác sau khi command script hoàn tất, tùy cách xử lý lỗi và luồng thực thi của ứng dụng.

### 7.1. Chạy script khi khởi động non-interactive

Có thể gọi command script từ process arguments:

    java -Dspring.shell.interactive.enabled=false -jar support-cli.jar script --file file:/opt/jobs/daily-report.shell

Runner non-interactive thực thi command script, command này đọc file rồi chạy các dòng lệnh. Cách này hữu ích khi muốn dùng cùng một file script trong cả phiên tương tác lẫn automation.

### 7.2. Cú pháp @file của NonInteractiveShellRunner

Javadoc của NonInteractiveShellRunner mô tả một cách truyền script khác: đặt ký tự @ trước tên file trong arguments của runner. Ví dụ về ý nghĩa:

    @/opt/jobs/daily-report.shell

Đây là cú pháp ở cấp runner, không phải command script và không phải một ScriptShellRunner riêng. Khi gọi từ launcher hoặc wrapper cụ thể, cần bảo đảm argument @file được chuyển nguyên vẹn tới Spring Shell. Nếu muốn cú pháp rõ ràng, dễ đọc và dùng cùng một cách trong nhiều môi trường, command script --file thường dễ tài liệu hóa hơn.

## 8. ShellRunner và Spring Boot startup

Trong ứng dụng Spring Boot, Spring Shell auto-configuration đăng ký một bean ApplicationRunner tên springShellApplicationRunner. Bean này gọi ShellRunner đã được cấu hình sau khi ApplicationContext khởi tạo.

Có thể hiểu luồng như sau:

    flowchart TD
        A[SpringApplication.run] --> B[Khởi tạo ApplicationContext]
        B --> C[Auto-configuration tạo ShellRunner]
        C --> D[Đăng ký springShellApplicationRunner]
        D --> E[Spring Boot gọi ApplicationRunner]
        E --> F[ShellRunner.run args]
        F --> G[Interactive hoặc NonInteractive]

Trong ứng dụng Spring Boot thông thường, không cần tự gọi runner từ main nếu starter/autoconfiguration đã thực hiện việc đó.

Nếu cần thay đổi logic khởi động, tài liệu Spring Shell cho phép cung cấp ApplicationRunner bean có tên springShellApplicationRunner để thay thế bean mặc định. Runner tùy chỉnh phải chuyển arguments phù hợp cho ShellRunner đã chọn. Không tạo một ApplicationRunner thứ hai rồi vô tình khởi chạy cùng shell lần nữa.

## 9. Dùng Spring Shell không qua Spring Boot

Trong ứng dụng Spring thuần, ứng dụng có thể khởi tạo context, lấy ShellRunner và gọi trực tiếp:

    @EnableCommand(SpringShellApplication.class)
    public class SpringShellApplication {

        public static void main(String[] args) throws Exception {
            ApplicationContext context =
                    new AnnotationConfigApplicationContext(SpringShellApplication.class);
            ShellRunner runner = context.getBean(ShellRunner.class);
            runner.run(args);
        }

        @Command
        public void hi() {
            System.out.println("Hello world!");
        }
    }

Ví dụ trên minh họa cách gọi API. Với cách cấu hình thuần Spring này, runner mặc định là SystemShellRunner; nếu cần JLine, phải đăng ký cấu hình và dependency JLine tương ứng.

Khi dùng Spring Boot, starter/autoconfiguration đảm nhiệm phần tạo runner và gọi nó. Khi dùng Spring thuần, ứng dụng kiểm soát trực tiếp thời điểm gọi run(args).

## 10. Chọn JLine hay System Console?

Việc chọn interactive runner phụ thuộc vào classpath và cách cấu hình ứng dụng.

| Nhu cầu | Lựa chọn |
|---|---|
| Prompt cơ bản, ít dependency | SystemShellRunner |
| Cần lịch sử command | JLineShellRunner |
| Cần tab completion | JLineShellRunner |
| Cần highlighter và trải nghiệm terminal phong phú | JLineShellRunner |
| Chạy command trong CI hoặc scheduler | NonInteractiveShellRunner |
| Chạy một file script rồi thoát | NonInteractiveShellRunner kết hợp command script |

Trong Spring Shell 4.x, spring-shell-core không phụ thuộc JLine. Nếu cần JLine, hãy kiểm tra dependency tree và xác nhận spring-shell-jline có mặt. Khi không có module JLine, việc bật interactive không tự cung cấp các tính năng riêng của JLine; ứng dụng dùng SystemShellRunner.

Không nên thêm JLine chỉ vì ứng dụng có command chạy non-interactive. NonInteractiveShellRunner không cần một phiên terminal giàu tính năng để thực thi command từ arguments.

## 11. Một runner cho mỗi ApplicationContext

Spring Shell 4.x thiết kế theo hướng chỉ sử dụng một ShellRunner trong một ApplicationContext. Không dùng đồng thời một interactive runner và một non-interactive runner để cùng nhận input trong cùng ứng dụng.

Lý do là hai runner đại diện cho hai cách điều khiển vòng đời khác nhau:

- Interactive runner giữ vòng lặp nhập lệnh và chờ người dùng.
- Non-interactive runner xử lý command đã được cung cấp rồi kết thúc.

Nếu một ứng dụng cần hai cách vận hành, hãy chọn mode theo profile hoặc property ở mỗi lần khởi chạy. Ví dụ, cùng một JAR có thể chạy interactive trên máy vận hành và non-interactive trong CI, nhưng mỗi process chỉ chọn một chế độ khi khởi động.

Không đăng ký thêm một bean ShellRunner cạnh runner auto-configured mà không thay thế cấu hình mặc định. Việc có nhiều bean có thể làm injection mơ hồ hoặc dẫn đến nhiều thành phần cùng cố gắng điều khiển shell.

## 12. Chọn runner tùy chỉnh

ShellRunner là interface nên ứng dụng có thể triển khai runner riêng nếu có nhu cầu đặc biệt, chẳng hạn nhận input từ một nguồn không phải console hoặc tích hợp với một bộ điều phối bên ngoài.

Trước khi viết runner tùy chỉnh, hãy xác định:

- Nguồn input là process arguments, file, socket hay một adapter khác.
- Cách runner xác định khi nào dừng.
- Cách xử lý lỗi parse và lỗi thực thi.
- Cách ghi output và flush dữ liệu.
- Cách kết thúc hoặc trả quyền điều khiển cho Spring Boot.
- Cách bảo đảm chỉ một runner được sử dụng trong ApplicationContext.

Runner tùy chỉnh cần thực hiện hợp đồng của ShellRunner.run(String[] args). Nếu ứng dụng Spring Boot dùng auto-configuration, phải cấu hình để runner mặc định không được tạo đồng thời hoặc thay thế đúng bean startup được Spring Shell sử dụng.

Không cần viết runner mới chỉ để chọn interactive hoặc non-interactive. Thuộc tính spring.shell.interactive.enabled đã xử lý lựa chọn đó.

## 13. Thay đổi quan trọng từ Spring Shell 3.x sang 4.x

Mô hình runner của 4.x khác với một số hướng dẫn 3.x. Không nên sao chép nguyên các property hoặc class cũ sang dự án mới.

| Nội dung | Spring Shell 3.x | Spring Shell 4.x |
|---|---|---|
| Runner | Có InteractiveShellRunner, NonInteractiveShellRunner, ScriptShellRunner trong mô hình 3.x | Có SystemShellRunner, JLineShellRunner, NonInteractiveShellRunner |
| Chọn mode | Các property runner riêng đã tồn tại trong các phiên bản 3.x | Chọn interactive/non-interactive bằng spring.shell.interactive.enabled |
| Mặc định | Có khác biệt giữa các minor version; từ 3.3 chỉ non-interactive runner được bật mặc định theo tài liệu 3.3 | Interactive mode bật mặc định |
| Có arguments khi khởi động | Quy tắc lựa chọn runner thay đổi theo phiên bản 3.x | Có arguments vẫn interactive nếu không tắt property |
| JLine | Thường có trong cấu hình/starter của các ứng dụng 3.x | Tách thành module spring-shell-jline |
| Command interactivity | Có InteractionMode để giới hạn command theo mode | InteractionMode đã bị loại bỏ; command không còn được đánh dấu interactive/non-interactive |
| Script | Có runner riêng trong mô hình 3.x | Dùng NonInteractiveShellRunner hoặc command tích hợp script |

Trong 4.x, không còn dùng InteractionMode.INTERACTIVE hoặc InteractionMode.NONINTERACTIVE để gắn lên command. Tất cả command được đăng ký cho shell và chạy trong mode mà ứng dụng đã chọn khi khởi động.

Nếu command chỉ có ý nghĩa trong một cách vận hành, hãy thiết kế hành vi và thông báo phù hợp với cả hai môi trường hoặc tổ chức command set theo cấu hình ứng dụng. Không sử dụng API InteractionMode của 3.x trong code 4.x.

## 14. Debug khi chọn runner

Spring Shell có thể bật debug mode bằng property:

    spring:
      shell:
        debug:
          enabled: true

Khi bật, Spring Shell cung cấp thông tin debug bổ sung trong interactive mode, bao gồm stack trace của lỗi để hỗ trợ phát triển và xử lý sự cố.

Khi runner không được chọn như mong đợi, kiểm tra:

- Giá trị thực tế của spring.shell.interactive.enabled.
- Profile và file cấu hình đang được nạp.
- Biến môi trường có ghi đè cấu hình hay không.
- spring-shell-jline có trên classpath hay không.
- Có bean ShellRunner hoặc ApplicationRunner tùy chỉnh nào thay thế auto-configuration không.
- Có nhiều thành phần cùng cố gắng khởi chạy shell không.

Nếu ứng dụng vẫn mở prompt khi mong đợi chạy một command, kiểm tra interactive property trước. Nếu ứng dụng chỉ có prompt cơ bản mà thiếu history hoặc completion, kiểm tra module JLine.

## 15. Kiểm thử runner và chế độ thực thi

Kiểm thử command method riêng lẻ chưa đủ để xác nhận runner được chọn đúng. Nên có kiểm thử tích hợp hoặc process test cho từng cách khởi chạy.

### 15.1. Kiểm thử interactive mode

- Khởi động context với spring.shell.interactive.enabled=true.
- Xác nhận đúng runner được tạo theo classpath.
- Gửi một command qua input provider hoặc test client.
- Xác nhận command thực thi và prompt tiếp tục chờ input.
- Nếu dùng JLine, kiểm tra history và completion trong môi trường terminal tương ứng.

### 15.2. Kiểm thử non-interactive mode

- Khởi động process với spring.shell.interactive.enabled=false.
- Truyền một command hợp lệ qua process arguments.
- Xác nhận command được thực thi.
- Xác nhận ứng dụng kết thúc thay vì chờ prompt.
- Kiểm tra output và exit status theo hợp đồng CLI.

### 15.3. Kiểm thử script

- Tạo file có nhiều command, mỗi command một dòng.
- Thêm comment bắt đầu bằng //.
- Gọi script --file với đường dẫn filesystem.
- Gọi lại với resource classpath:.
- Xác nhận thứ tự thực thi và cách xử lý khi một command lỗi.
- Kiểm tra file không tồn tại hoặc không đọc được.

Ma trận kiểm thử:

| Cấu hình | Arguments | Kết quả mong đợi |
|---|---|---|
| Interactive mặc định | Không có command | Mở prompt |
| Interactive mặc định | Có command arguments | Vẫn mở interactive mode theo cấu hình 4.x |
| Interactive = false | Một command hợp lệ | Chạy command rồi kết thúc |
| Interactive = false | Command không tồn tại | Báo lỗi thực thi theo cơ chế command |
| Interactive = false | script --file file:/... | Chạy các dòng trong script rồi kết thúc |
| Interactive = true, có JLine | Không có command | Mở JLine shell |
| Interactive = true, không có JLine | Không có command | Mở System Console shell |

### 15.4. Kiểm thử trong môi trường gần với triển khai

Một test chạy trong IDE có thể khác khi chạy JAR từ terminal hoặc container. Với interactive runner, kiểm tra process có console/terminal phù hợp. Với non-interactive runner, kiểm tra arguments, encoding, đường dẫn file và output khi stdout/stderr được chuyển hướng.

Không dùng việc ứng dụng khởi động thành công làm bằng chứng duy nhất rằng runner đã chọn đúng. Hãy xác nhận hành vi thực tế: có prompt hay không, command có được thực thi, process có kết thúc và script có chạy theo thứ tự.

## 16. Những lỗi thường gặp

### Truyền command arguments nhưng ứng dụng vẫn mở prompt

Trong 4.x, interactive mode bật mặc định kể cả khi process có arguments. Đặt spring.shell.interactive.enabled=false trước khi khởi động để dùng NonInteractiveShellRunner.

### Dùng property cũ của ScriptShellRunner

Không sao chép cấu hình runner riêng của 3.x sang 4.x. Trong 4.x, dùng non-interactive mode và command script --file khi cần chạy file script.

### Không có tab completion dù đã bật interactive

Kiểm tra spring-shell-jline có trên classpath không. Interactive mode có thể dùng SystemShellRunner nếu không có JLine; runner này không cung cấp các tính năng nâng cao của JLine.

### Có nhiều bean ShellRunner

Kiểm tra cấu hình tùy chỉnh và auto-configuration. Spring Shell 4.x yêu cầu một runner được sử dụng trong mỗi ApplicationContext.

### Command 3.x có InteractionMode không biên dịch trong 4.x

InteractionMode đã bị loại bỏ ở 4.x. Xóa cấu hình mode cấp command và thiết kế command phù hợp với mode mà ứng dụng chọn khi khởi động.

### Script chạy được trong prompt nhưng không chạy lúc khởi động

Kiểm tra ứng dụng có đang ở non-interactive mode không và arguments có gọi command script --file đúng cú pháp không. Command script là một command bình thường được thực thi bởi runner đã chọn.

### Dùng nhầm JVM option thành command option

Đặt -Dspring.shell.interactive.enabled=false trước -jar. Các command và option của Spring Shell đặt sau tên JAR.

### Dùng JLine dependency nhưng runner vẫn không phải JLine

Kiểm tra dependency thực tế, starter và điều kiện auto-configuration. Cũng kiểm tra có cấu hình runner tùy chỉnh hoặc property interactive bị tắt hay không.

## 17. Checklist chọn runner trước khi phát hành

- [ ] Đã quyết định ứng dụng cần prompt tương tác hay thực thi command rồi thoát.
- [ ] Đã đặt spring.shell.interactive.enabled trước khi khởi động.
- [ ] Đã hiểu interactive mặc định là true trong Spring Shell 4.x.
- [ ] Đã chọn JLineShellRunner nếu cần history, completion và tính năng terminal nâng cao.
- [ ] Đã chấp nhận SystemShellRunner nếu chỉ cần Console cơ bản.
- [ ] Đã chọn NonInteractiveShellRunner cho command arguments và automation.
- [ ] Không đăng ký nhiều runner để chạy đồng thời trong cùng ApplicationContext.
- [ ] Nếu dùng Spring Boot, đã hiểu vai trò của springShellApplicationRunner.
- [ ] Nếu cần script, đã chọn script --file hoặc cú pháp script ở cấp runner.
- [ ] Đã phân biệt script command với ScriptShellRunner của mô hình 3.x.
- [ ] Đã loại bỏ cấu hình InteractionMode cũ khi nâng cấp 4.x.
- [ ] Đã kiểm thử prompt, process arguments, script, output và exit status.

## 18. Tự kiểm tra

**Câu 1.** ShellRunner chịu trách nhiệm chính về việc gì?

**Gợi ý trả lời:** Nó điều khiển cách shell nhận input và thực thi command trong một chế độ cụ thể, thông qua phương thức run(String[] args).

**Câu 2.** Ba runner tích hợp trong Spring Shell 4.x là gì?

**Gợi ý trả lời:** SystemShellRunner, JLineShellRunner và NonInteractiveShellRunner.

**Câu 3.** Property nào chọn interactive hay non-interactive mode?

**Gợi ý trả lời:** spring.shell.interactive.enabled. Giá trị mặc định là true; đặt false để dùng non-interactive runner.

**Câu 4.** Vì sao command arguments không tự làm ứng dụng chuyển sang non-interactive trong 4.x?

**Gợi ý trả lời:** Vì interactive mode được bật mặc định và vẫn được giữ ngay cả khi process có arguments. Muốn chạy command rồi thoát phải tắt interactive trước khi runner khởi động.

**Câu 5.** Khi nào dùng JLineShellRunner thay cho SystemShellRunner?

**Gợi ý trả lời:** Khi cần history, tab completion, highlighter hoặc các tính năng terminal nâng cao. JLine phải có trên classpath, thường qua module spring-shell-jline hoặc starter phù hợp.

**Câu 6.** script --file có phải là một ShellRunner riêng trong 4.x không?

**Gợi ý trả lời:** Không. Đó là command tích hợp được thực thi bởi runner đã chọn. Spring Shell 4.x không còn ScriptShellRunner như mô hình 3.x.

**Câu 7.** InteractionMode cấp command còn được dùng trong 4.x không?

**Gợi ý trả lời:** Không. API này đã bị loại bỏ; ứng dụng chọn mode ở cấp runner khi khởi động và command không còn được gắn nhãn interactive/non-interactive.

## Kết luận

Spring Shell 4.x chọn cách vận hành shell ngay khi ứng dụng khởi động. SystemShellRunner cung cấp prompt cơ bản bằng Java Console; JLineShellRunner bổ sung trải nghiệm terminal nâng cao; NonInteractiveShellRunner chạy command hoặc script rồi kết thúc. Mỗi ApplicationContext chỉ sử dụng một runner.

spring.shell.interactive.enabled là công tắc chính: mặc định true, đặt false để chạy command từ process arguments. Có arguments không tự làm ứng dụng chuyển sang non-interactive. Khi cần script, có thể gọi command script --file; command này chạy trên runner đã chọn và không phải một runner riêng.

Khi nâng cấp từ 3.x, cần bỏ các cấu hình runner riêng cũ và InteractionMode cấp command. Hãy chọn mode theo môi trường triển khai, xác nhận dependency JLine nếu cần, rồi kiểm thử hành vi thực tế của process và script. Cách cấu hình này giúp cùng một CLI phục vụ người vận hành, automation và pipeline với vòng đời rõ ràng.

## Tài liệu tham khảo

- [Spring Shell 4.0.4 — Execution](https://docs.spring.io/spring-shell/reference/execution.html)
- [Spring Shell 4.0.4 — ShellRunner API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/ShellRunner.html)
- [Spring Shell 4.0.4 — SystemShellRunner API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/SystemShellRunner.html)
- [Spring Shell 4.0.4 — JLineShellRunner API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/JLineShellRunner.html)
- [Spring Shell 4.0.4 — NonInteractiveShellRunner API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/NonInteractiveShellRunner.html)
- [Spring Shell 4.0.4 — Script command](https://docs.spring.io/spring-shell/reference/commands/builtin/script.html)
- [Spring Shell 4.x — Migration guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide)
