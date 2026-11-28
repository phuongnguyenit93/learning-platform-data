# Log chen vào đầu ra làm hỏng JSON hoặc CSV

Một command Spring Shell có thể trả JSON hoặc CSV để script, CI/CD hay chương trình khác xử lý. Nếu output chứa thêm dòng như banner Spring Boot, log INFO, prompt, thông báo debug hoặc nội dung in trực tiếp từ thư viện, parser sẽ đọc cả những dòng đó như dữ liệu và báo lỗi.

Ví dụ file JSON dự kiến chỉ có một mảng:

```text
[
  {"id":"P101","name":"Portal"},
  {"id":"P102","name":"Inventory"}
]
```

Nhưng file thực tế lại bắt đầu bằng log:

```text
2026-11-26 09:15:12 INFO 12345 --- [main] c.e.shell.ProjectApplication : Starting ProjectApplication
[
  {"id":"P101","name":"Portal"},
  {"id":"P102","name":"Inventory"}
]
```

JSON parser không biết dòng đầu là log. Nó chỉ thấy dữ liệu không hợp lệ trước dấu ngoặc mở mảng. Với CSV, các dòng log có thể bị coi là record đầu tiên hoặc làm lệch số cột.

Để xử lý đúng, cần xác định dòng thừa đến từ đâu rồi đưa dữ liệu command và thông tin chẩn đoán về đúng kênh. Spring Shell 3.4.3 có hướng dẫn riêng cho trường hợp log console trộn vào output command; Spring Boot cũng cung cấp thuộc tính để tắt banner, giảm startup information và cấu hình file log.

## 1. Phân biệt các nguồn đầu ra

Không phải mọi dòng xuất hiện trước kết quả đều là logging. Hãy phân loại trước khi sửa:

| Nội dung quan sát được | Nguồn có thể gây ra | Hướng kiểm tra |
| --- | --- | --- |
| Khối ASCII và dòng phiên bản | Spring Boot banner | Kiểm tra spring.main.banner-mode |
| Starting..., Started..., No active profile... | Spring Boot startup information | Kiểm tra spring.main.log-startup-info |
| Timestamp, level INFO/WARN/ERROR, tên logger | Logging system | Kiểm tra logging.pattern.console và appender |
| Dòng shell:> hoặc prompt nhập liệu | Interactive runner | Kiểm tra chế độ chạy command |
| Debug, progress, lời chào do ứng dụng in | Code ứng dụng hoặc thư viện | Tìm System.out/System.err và output writer |
| Dòng kết quả có cấu trúc | Command | Kiểm tra serializer và định dạng dữ liệu |

Tắt banner không tắt log. Giảm log level không loại bỏ prompt. Cấu hình logging cũng không chặn một thư viện tự gọi System.out.println. Mỗi nguồn phải được xử lý bằng đúng cơ chế của nó.

## 2. Tái hiện và thu riêng stdout, stderr

Trước tiên, chạy command và lưu hai stream ra hai file để xem dòng nhiễu nằm ở đâu:

```bash
./bin/spring-shell project export-json > stdout.txt 2> stderr.txt
```

Mở đầu mỗi file:

```bash
head -n 20 stdout.txt
head -n 20 stderr.txt
```

Nếu output JSON nằm trong stdout.txt cùng các dòng log, parser sẽ thất bại khi đọc stdout. Nếu log nằm trong stderr.txt còn stdout.txt chỉ chứa JSON, có thể pipe stdout sang parser mà không trộn hai luồng:

```bash
./bin/spring-shell project export-json 2> diagnostics.log | jq .
```

Tuy nhiên, không mặc định rằng log Spring Boot luôn nằm ở stderr. Vị trí ghi phụ thuộc logging implementation và appender đang dùng; cấu hình console mặc định có thể ghi vào cùng console stream với dữ liệu command. Chuyển hướng **2>** chỉ tách stderr. Nếu log đang nằm trên stdout, nó vẫn làm hỏng JSON/CSV.

Không dùng **2>&1** khi mục tiêu là tách dữ liệu khỏi chẩn đoán. Lệnh này nhập stderr vào stdout, khiến hai loại nội dung lại nằm chung một luồng.

Nếu cần kiểm tra process trong test Java, dùng **ProcessBuilder** và chuyển từng stream vào file riêng:

```java
Path stdoutFile = Files.createTempFile("shell-output-", ".json");
Path stderrFile = Files.createTempFile("shell-error-", ".log");

Process process = new ProcessBuilder(
        nativeOrJarLauncher,
        "project",
        "export-json"
)
        .redirectOutput(stdoutFile.toFile())
        .redirectError(stderrFile.toFile())
        .start();

int exitCode = process.waitFor();
String json = Files.readString(stdoutFile);
String diagnostics = Files.readString(stderrFile);

assertThat(exitCode).isZero();
assertThat(json).startsWith("[");
```

Ví dụ dùng biến **nativeOrJarLauncher** đại diện cho lệnh chạy ứng dụng trong test; với executable JAR, có thể dùng **java** làm executable và thêm các argument **-jar**, đường dẫn JAR trước tên command. Việc ghi ra file riêng giúp tránh đọc tuần tự hai pipe và làm test dễ xác định stream gây nhiễu.

## 3. Tắt banner và startup information của Spring Boot

Nếu dòng thừa là banner ASCII, đặt:

```yaml
spring:
  main:
    banner-mode: off
```

Các giá trị của **spring.main.banner-mode**:

| Giá trị | Hành vi |
| --- | --- |
| console | In banner ra console |
| log | Gửi banner qua logger |
| off | Không tạo banner |

Nếu các dòng thừa có dạng Starting..., Started... hoặc No active profile set..., đặt:

```yaml
spring:
  main:
    log-startup-info: false
```

Có thể kết hợp:

```yaml
spring:
  main:
    banner-mode: off
    log-startup-info: false
```

Hai thuộc tính này chỉ xử lý banner và startup information. Các logger khác trong lúc khởi tạo context, thư viện kết nối database hoặc code của ứng dụng vẫn có thể ghi log. Nếu sau khi tắt chúng mà parser vẫn lỗi, hãy tiếp tục kiểm tra logging system và output của command.

## 4. Tắt console logging nhưng vẫn lưu log vào file

Đây là cách xử lý trực tiếp khi log framework chen vào kết quả command. Spring Shell 3.4.3 hướng dẫn đặt console logging pattern thành giá trị rỗng:

```yaml
logging:
  pattern:
    console: ""
```

Nếu vẫn cần log để điều tra sự cố, cấu hình file output cùng lúc:

```yaml
logging:
  pattern:
    console: ""
  file:
    name: logs/spring-shell.log
  level:
    root: INFO
```

Khi dùng cấu hình mặc định của Spring Boot:

- Console logging không tạo dòng log trên console.
- Logger vẫn ghi vào file được chỉ định bởi logging.file.name.
- Các mức INFO, WARN và ERROR vẫn được giữ trong file theo log level đã chọn.
- Command tiếp tục ghi dữ liệu qua shell output.

Một điểm dễ nhầm: chỉ đặt **logging.file.name** sẽ thêm file output; nó không tự tắt console logging. Muốn giữ log ở file mà không làm nhiễu stdout, cần cấu hình cả **logging.pattern.console: ""**.

Đường dẫn tương đối như **logs/spring-shell.log** được tính từ working directory của tiến trình. Đảm bảo thư mục tồn tại hoặc tài khoản chạy ứng dụng có quyền tạo thư mục và ghi file. Trong môi trường production, có thể dùng đường dẫn tuyệt đối và chính sách rotate log phù hợp.

### Vì sao không chỉ đặt root thành WARN?

Cấu hình sau chỉ loại bỏ log thấp hơn WARN:

```yaml
logging:
  level:
    root: WARN
```

WARN và ERROR vẫn có thể xuất hiện trên console và làm hỏng JSON/CSV. Nếu hợp đồng yêu cầu stdout chỉ có dữ liệu, hãy tắt console logging hoặc định tuyến log ra file/stream riêng. Log level là công cụ giảm độ chi tiết, không phải cách bảo đảm stdout sạch.

Không đặt **logging.level.root: OFF** chỉ để chữa lỗi parse. Cấu hình đó cũng ẩn cảnh báo và lỗi vận hành. Nếu tắt console, hãy giữ một kênh chẩn đoán có thể kiểm tra được.

## 5. Dùng cấu hình phù hợp với Spring Shell

Spring Shell 3.4.3 lưu ý rằng truyền cấu hình logging dưới dạng option command line của shell không được hỗ trợ như cách cấu hình logging. Vì vậy, không nên giả định lệnh sau sẽ luôn được hiểu là cấu hình Spring Boot:

```bash
java -jar spring-shell.jar --logging.pattern.console= project export-json
```

Sau tên JAR, argument được đưa vào luồng phân tích command của shell; option đó có thể bị hiểu là option của command hoặc gây lỗi cú pháp. Dùng một trong các cách sau để cấu hình trước khi command chạy:

**File application.yml**

```yaml
spring:
  main:
    banner-mode: off
    log-startup-info: false

logging:
  pattern:
    console: ""
  file:
    name: logs/spring-shell.log
```

**Biến môi trường**

```bash
SPRING_MAIN_BANNER_MODE=off \
SPRING_MAIN_LOG_STARTUP_INFO=false \
LOGGING_PATTERN_CONSOLE="" \
LOGGING_FILE_NAME=logs/spring-shell.log \
java -jar spring-shell.jar project export-json
```

**JVM system property**

```bash
java \
  -Dspring.main.banner-mode=off \
  -Dspring.main.log-startup-info=false \
  -Dlogging.pattern.console= \
  -Dlogging.file.name=logs/spring-shell.log \
  -jar spring-shell.jar project export-json
```

Các tùy chọn **-D...** phải đứng trước **-jar**. Java launcher xử lý chúng như system property của JVM; phần sau tên JAR là argument ứng dụng.

Nếu đã đặt đúng thuộc tính nhưng log vẫn xuất hiện, kiểm tra profile đang active, file cấu hình bên ngoài và các nguồn cấu hình có độ ưu tiên cao hơn. Spring Boot đọc config data, biến môi trường và system property theo thứ tự ưu tiên; một giá trị được đặt ở nguồn ưu tiên cao hơn có thể ghi đè cấu hình trong application.yml.

## 6. Kiểm tra custom Logback hoặc Log4j2 configuration

Thuộc tính **logging.pattern.console** hoạt động với cấu hình logging mặc định của Spring Boot. Nếu dự án có file cấu hình riêng, cần kiểm tra appender đang thực sự ghi ra đâu.

Các file thường gặp:

| Logging implementation | File cấu hình |
| --- | --- |
| Logback | logback-spring.xml, logback.xml |
| Log4j2 | log4j2-spring.xml, log4j2.xml |
| Java Util Logging | logging.properties |

Spring Boot khởi tạo logging trước khi ApplicationContext được tạo. Vì vậy, đặt logging property bằng **@PropertySource** trong một class **@Configuration** thường là quá muộn để điều khiển logging ban đầu. Hãy dùng application.yml, external config, biến môi trường, JVM system property hoặc file cấu hình logging được nạp từ đầu.

Nếu có custom appender:

1. Tìm appender loại console và xác định target stream.
2. Kiểm tra logger root và logger package có gắn appender đó hay không.
3. Kiểm tra additivity để tránh một log event được ghi qua nhiều appender.
4. Xác định file appender có hoạt động và có quyền ghi hay không.
5. Kiểm tra profile hoặc logging.config có chọn một file cấu hình khác trong môi trường chạy.

Không chỉ xóa appender khỏi cấu hình mà không thay bằng đích log khác nếu vận hành vẫn cần chẩn đoán. Hãy định tuyến log tới file, hệ thống thu thập log hoặc stderr theo hợp đồng của ứng dụng.

## 7. Đưa nội dung command qua shell output writer

Một nguyên nhân khác là code ứng dụng tự ghi dữ liệu hoặc thông báo vào standard output. Trong Spring Shell 4.x, cách được khuyến nghị để ghi kết quả command là lấy **PrintWriter** từ **CommandContext.outputWriter()**:

```java
@Command(name = "project export-json")
public void exportJson(CommandContext context) throws JsonProcessingException {
    String json = objectMapper.writeValueAsString(projectService.findAll());

    context.outputWriter().println(json);
    context.outputWriter().flush();
}
```

**System.out.println(...)** ghi thẳng vào stream của JVM. Nội dung này có thể nằm ngoài writer mà shell hoặc test client đang quản lý, đồng thời chen vào stdout mà script cần parse. Hãy phân loại:

| Nội dung | Nên ghi ở đâu |
| --- | --- |
| JSON/CSV hoặc kết quả command | CommandContext.outputWriter() |
| Debug, thông tin tiến trình, thời gian xử lý | Logger |
| Cảnh báo/lỗi cần người gọi đọc riêng | Logger/appender theo quy ước stderr hoặc file |
| File báo cáo được export | Writer/stream riêng do command tạo và quản lý |

Không in các dòng như **Đang xuất dữ liệu...**, **Hoàn tất** hoặc stack trace vào cùng stdout khi command cam kết trả JSON/CSV thuần. Nếu cần thông báo tiến độ, ghi qua logger hoặc một kênh tiến độ riêng được ứng dụng công bố.

Không vừa ghi kết quả qua **outputWriter()** vừa return lại cùng một chuỗi nếu framework cũng tự in return value. Điều đó có thể khiến dữ liệu xuất hiện hai lần.

## 8. Kiểm tra prompt và interactive runner

Nếu dòng thừa là prompt, cursor control hoặc ký tự ANSI, đó có thể là interactive shell chứ không phải logging. Một command dùng cho pipeline nên chạy ở non-interactive mode theo cấu hình của phiên bản Spring Shell đang dùng.

Kiểm tra:

- Interactive runner có đang được bật trong môi trường script không?
- Ứng dụng có đang chờ prompt hoặc đọc input không?
- Command có bật progress bar, spinner hoặc màu ANSI không?
- Output có chứa ký tự điều khiển terminal không?

Với command cần trả dữ liệu máy đọc, không khởi chạy một phiên terminal tương tác. Nếu cần một lệnh vừa hỗ trợ interactive vừa hỗ trợ automation, hãy bảo đảm nhánh non-interactive không in prompt, banner riêng của ứng dụng hoặc tiến độ dạng spinner.

## 9. Phân biệt log nhiễu với JSON/CSV sai định dạng

Không phải mọi lỗi parse đều do logging. Hãy xem vị trí lỗi và nội dung quanh đó:

| Dấu hiệu | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| JSON lỗi ngay ký tự đầu tiên | Banner, log hoặc prompt đứng trước JSON | Xem các dòng đầu của stdout |
| JSON hợp lệ ở đầu nhưng có dòng INFO ở cuối | Log được ghi sau kết quả command hoặc lúc shutdown | Kiểm tra toàn bộ stdout và logger shutdown |
| JSON có ký tự escape ANSI | Màu hoặc terminal control sequence | Tắt màu/progress UI trong non-interactive mode |
| CSV có thêm record đầu hoặc cuối | Log hoặc thông báo bị trộn vào stream | Mở file bằng text editor và kiểm tra từng dòng |
| CSV lỗi ở một cột giữa dữ liệu | Giá trị chứa dấu phẩy, dấu nháy hoặc newline chưa được escape | Kiểm tra serializer CSV và parse bằng CSV parser |
| JSON lỗi ở giữa một object | Serializer, encoding hoặc dữ liệu bị cắt | Kiểm tra output writer, exception và exit code |

Nếu stdout bắt đầu bằng JSON hợp lệ nhưng parser lỗi ở một trường dữ liệu, đừng tiếp tục thay logging config. Kiểm tra serializer, encoding UTF-8, escape ký tự và dữ liệu đầu vào.

Với CSV, một giá trị như **Portal, Billing** phải được quote đúng chuẩn. Nếu không, parser có thể đọc thành hai cột dù không có log nào chen vào. Đây là lỗi định dạng CSV, không phải lỗi logging.

## 10. Xác thực output bằng parser

Sau khi sửa, kiểm tra dữ liệu bằng parser thật thay vì chỉ nhìn terminal:

**JSON**

```bash
./bin/spring-shell project export-json > result.json
jq -e . result.json
```

Nếu command trả một mảng, có thể kiểm tra kiểu dữ liệu:

```bash
jq -e 'type == "array"' result.json
```

**CSV**

Có thể kiểm tra file CSV bằng parser CSV của ngôn ngữ hoặc công cụ được pipeline sử dụng. Không chỉ đếm dấu phẩy trên mỗi dòng vì trường CSV hợp lệ có thể chứa dấu phẩy hoặc newline bên trong dấu nháy.

Kiểm tra thêm:

- stdout chỉ chứa một định dạng đã công bố.
- stderr không chứa nội dung dữ liệu bị lặp.
- Exit code phản ánh thành công/thất bại của command.
- Log file có đủ thông tin chẩn đoán.
- Kết quả không đổi khi chạy từ thư mục hiện tại khác.
- Không có banner, prompt hoặc ANSI control sequence trong output máy đọc.

Một pipeline Bash có thể giữ exit code của command khi parse qua pipe bằng **set -o pipefail**:

```bash
set -o pipefail
./bin/spring-shell project export-json | jq -e 'type == "array"'
```

Không dùng riêng mã thoát của **jq** để kết luận command thành công nếu pipeline không giữ mã thoát của tiến trình trước đó.

## 11. Quy trình xử lý sự cố từng bước

Khi nhận báo lỗi kiểu **Invalid JSON**, **CSV parse error** hoặc script không đọc được output:

1. Chạy command và lưu stdout, stderr vào hai file riêng.
2. Đọc đầu và cuối stdout để tìm banner, startup log, prompt hoặc dòng thừa.
3. Nếu là banner, đặt **spring.main.banner-mode=off**.
4. Nếu là startup information, đặt **spring.main.log-startup-info=false**.
5. Nếu là logger, đặt **logging.pattern.console: ""** và cấu hình **logging.file.name**.
6. Nếu log vẫn xuất hiện, kiểm tra custom appender, profile, logging.config và nguồn cấu hình ghi đè.
7. Nếu nội dung đến từ code, chuyển chẩn đoán sang logger và kết quả sang **CommandContext.outputWriter()**.
8. Nếu là prompt hoặc ANSI, chuyển sang non-interactive runner và tắt UI tiến độ.
9. Chạy lại parser JSON/CSV trên stdout.
10. Kiểm tra exit code và xác nhận log vẫn được lưu ở nơi cần thiết.

## 12. Bảng lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| JSON bắt đầu bằng dòng timestamp INFO | Console logger ghi cùng stdout | Đặt console pattern rỗng, lưu log vào file |
| JSON bắt đầu bằng banner ASCII | Spring Boot banner đang bật | Đặt spring.main.banner-mode=off |
| JSON có dòng Starting/Started | Startup information còn bật | Đặt spring.main.log-startup-info=false |
| Đã đặt logging.file.name nhưng console vẫn có log | File output được thêm vào, console chưa bị tắt | Kết hợp logging.pattern.console rỗng |
| WARN/ERROR vẫn chen vào output sau khi đặt root WARN | WARN/ERROR vẫn được phép ghi | Tắt console appender/pattern, không chỉ đổi log level |
| Thuộc tính logging truyền sau tên JAR không có tác dụng | Spring Shell phân tích argument theo command; logging CLI properties không được hỗ trợ theo cách đó | Dùng application.yml, env hoặc -D trước -jar |
| Log vẫn xuất hiện dù console pattern rỗng | Custom Logback/Log4j2 appender hoặc logger tự ghi console | Kiểm tra file logging.config và appender |
| Lời chào vẫn chen vào JSON | ApplicationReadyEvent/listener tự in ra console | Chuyển sang logger hoặc chỉ hiển thị trong interactive mode |
| Dữ liệu xuất hiện hai lần | Vừa ghi writer vừa return cùng kết quả | Chọn một cách xuất output |
| Parser lỗi ở giữa CSV | CSV field chưa được escape | Dùng CSV serializer/parser đúng chuẩn |
| Output có ký tự màu hoặc spinner | Interactive UI hoặc ANSI output | Chạy non-interactive và tắt màu/progress |
| Không còn log để điều tra sau khi sửa | Đã tắt cả logging hoặc root level OFF | Bật file logging và kiểm tra quyền ghi |

## 13. Checklist phòng ngừa

- Xác định rõ stdout là dữ liệu command và logger là thông tin chẩn đoán.
- Tắt banner khi command được dùng cho JSON/CSV.
- Tắt startup information nếu không cần trong luồng máy đọc.
- Đặt **logging.pattern.console: ""** khi console phải sạch.
- Dùng **logging.file.name** để giữ log sau khi tắt console logging.
- Không cho rằng **logging.file.name** tự tắt console.
- Không dùng root level WARN như một bảo đảm stdout sạch.
- Không truyền logging property như option của command sau tên JAR.
- Kiểm tra custom Logback/Log4j2 appender và profile đang active.
- Dùng **CommandContext.outputWriter()** để ghi dữ liệu command trong Spring Shell 4.x.
- Không dùng **System.out.println(...)** cho log hoặc tiến độ.
- Chạy non-interactive khi output được pipe sang parser.
- Kiểm tra CSV escaping và JSON serialization riêng với logging.
- Test stdout, stderr, exit code và log file như các đầu ra độc lập.

## Tài liệu tham khảo

- [Spring Shell 3.4.3 — Logging](https://docs.spring.io/spring-shell/reference/3.4/customization/logging.html)
- [Spring Shell 4.0.3 — Command Context](https://docs.spring.io/spring-shell/reference/commands/context.html)
- [Spring Shell 4.0.3 — Writing Output](https://docs.spring.io/spring-shell/reference/commands/writing.html)
- [Spring Boot 3.4 — Logging](https://docs.spring.io/spring-boot/3.4/reference/features/logging.html)
- [Spring Boot 3.4 — SpringApplication và startup information](https://docs.spring.io/spring-boot/3.4/reference/features/spring-application.html)
- [Spring Boot 3.4 — Externalized Configuration](https://docs.spring.io/spring-boot/3.4/reference/features/external-config.html)
