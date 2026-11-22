# Màu terminal trong Java Console Logging

**Màu terminal** (*terminal colors*) là cách làm nổi bật thông tin khi chương trình ghi log ra console: ví dụ level `ERROR` hiển thị màu đỏ, `WARN` màu vàng, `INFO` màu xanh hoặc xám. Phần lớn terminal thực hiện điều này bằng **ANSI escape sequences**, tức là các byte điều khiển được chèn vào chuỗi đầu ra. Terminal hiểu các byte đó thì thay đổi màu hoặc kiểu chữ; hệ thống không hiểu chúng có thể hiển thị ký tự lạ như `^[ [31m` hoặc lưu cả các byte điều khiển vào file.

Màu chỉ là **lớp trình bày**. Một sự kiện `ERROR` không trở nên nghiêm trọng hơn nhờ màu đỏ, và một sự kiện `INFO` không mất ý nghĩa khi tắt màu. Trong logging thực tế, việc quyết định **ghi sự kiện nào** thuộc logger/level/filter; **ghi ở đâu** thuộc console handler/appender; còn **hiển thị màu ra sao** thường thuộc formatter/layout/encoder.

Mục tiêu của bài: hiểu ANSI SGR, chọn màu có ý nghĩa, phân biệt TTY với file/CI, bật/tắt màu đúng cách trong Java 17 và cấu hình của **Logback**, **Log4j 2** cũng như **java.util.logging (JUL)**. Các ví dụ giải thích rõ khi nào màu là dữ liệu thật trong stdout và khi nào chỉ là cách terminal hiển thị.

## 1. Màu terminal hoạt động như thế nào?

Một terminal hỗ trợ ANSI có thể nhận chuỗi:

```text
ESC [ 31 m   ERROR   ESC [ 0 m
```

Trong đó `ESC` là ký tự điều khiển U+001B (hex `1B`, decimal `27`), `[` bắt đầu một *Control Sequence Introducer* và `31m` là lệnh đặt màu chữ đỏ. `0m` là lệnh **reset** về thuộc tính hiển thị mặc định. Trên màn hình hỗ trợ, người dùng nhìn thấy chữ `ERROR` màu đỏ; trong byte stream vẫn có những ký tự ESC và tham số SGR.

Trong Java, có thể tạo tiền tố màu đỏ bằng:

```java
String red = "\u001B[31m";
String reset = "\u001B[0m";
System.out.println(red + "ERROR" + reset + " | event=job.failed");
```

Đây là **đoạn mã minh họa trong phương thức**, không phải class Java độc lập. Màu chỉ xuất hiện nếu terminal đang nhận stdout và hỗ trợ ANSI; nếu output bị chuyển đến file, file có thể chứa cả byte ESC. Phần chương trình hoàn chỉnh ở mục 6 có cơ chế bật/tắt màu để tránh điều đó.

**ANSI SGR** (*Select Graphic Rendition*) là nhóm lệnh thay đổi thuộc tính hiển thị như foreground, background, bold, underline và reset. Phần sau dấu `[` là các mã số, thường được ngăn bằng dấu `;` và kết thúc bằng `m`. Không phải mọi terminal thể hiện cùng một sắc độ; người dùng có thể đổi theme, palette, contrast và độ sáng.

### Các mã SGR cơ bản

| Mã | Ý nghĩa thường gặp | Chuỗi biểu diễn trong Java |
| --- | --- | --- |
| `0` | Reset các thuộc tính SGR. | `"\u001B[0m"` |
| `1` | Bold hoặc tăng độ đậm/cường độ tùy terminal. | `"\u001B[1m"` |
| `2` | Dim/faint khi terminal hỗ trợ. | `"\u001B[2m"` |
| `4` | Underline. | `"\u001B[4m"` |
| `30`–`37` | Màu chữ chuẩn: đen, đỏ, xanh lá, vàng, xanh dương, tím, cyan, trắng. | `"\u001B[31m"` là đỏ |
| `90`–`97` | Nhóm màu chữ sáng/bright khi được hỗ trợ. | `"\u001B[91m"` là bright red |
| `40`–`47` | Màu nền chuẩn. | `"\u001B[43m"` là nền vàng |
| `39` | Khôi phục màu chữ mặc định của terminal. | `"\u001B[39m"` |
| `49` | Khôi phục màu nền mặc định. | `"\u001B[49m"` |

Ví dụ màu chữ xanh lá là `ESC[32m`, màu vàng là `ESC[33m`, màu đỏ là `ESC[31m`. Trong ví dụ thông dụng, chuỗi kết thúc màu là `ESC[0m`; nên reset ngay sau **đúng đoạn cần tô màu** để không làm cả phần console tiếp theo cũng bị đổi màu.

### Màu 256 và true color

Một số terminal hiện đại hỗ trợ thêm:

- **Màu 256:** `ESC[38;5;196m` chọn màu chữ từ bảng 256 màu; `ESC[48;5;N m` là mẫu khái niệm cho màu nền (bỏ khoảng trắng trước `m` và thay `N` bằng giá trị 0–255).
- **RGB/true color:** `ESC[38;2;255;80;80m` đặt foreground RGB (255,80,80) nếu terminal hỗ trợ.
- **Kết hợp:** `ESC[1;31m` thường có ý nghĩa bold + red.

Mã số không cam kết màu hiển thị tuyệt đối: terminal có thể không hỗ trợ 256 màu/true color, đổi palette hoặc dùng theme tối/sáng. Bảng màu chuẩn là điểm bắt đầu hợp lý cho logging; đừng phụ thuộc vào đúng mã RGB để xác định severity.

## 2. Nên tô màu thông tin nào trong log?

Tô cả dòng log theo level có thể gây chói và khó đọc khi thông điệp dài. Một quy ước thường dễ theo dõi hơn là chỉ **tô nhãn level** hoặc vài trường ổn định:

```text
INFO  | event=service.ready
WARN  | event=cache.fallback outcome=recovered
ERROR | event=job.failed outcome=failed
```

Trong phần văn bản này màu không được mã hóa; khi terminal thật hỗ trợ ANSI, level có thể mang màu riêng. Một mapping gợi ý khi **tự thiết kế**:

| Level | Màu tham khảo | Mục đích |
| --- | --- | --- |
| `TRACE` / `DEBUG` | Xám hoặc cyan dịu | Thông tin chẩn đoán, không cần nổi bật quá mức. |
| `INFO` | Màu mặc định hoặc xanh lá | Diễn biến bình thường đáng theo dõi. |
| `WARN` / `WARNING` | Vàng | Tình huống bất thường, có thể đã phục hồi. |
| `ERROR` / `SEVERE` | Đỏ | Thất bại thực tế cần điều tra. |
| `FATAL` khi API/backend có level này | Đỏ đậm hoặc đậm chữ | Mức nghiêm trọng đặc biệt theo quy ước riêng của backend. |

**Không có chuẩn bắt buộc “INFO phải xanh, WARN phải vàng”** cho mọi framework. Ví dụ `%highlight` của Logback và Log4j 2 có **palette mặc định khác nhau**; dùng cấu hình màu của chính backend hoặc tùy chỉnh rõ ràng nếu tổ chức cần nhất quán.

### Không dùng màu làm tín hiệu duy nhất

Người dùng có thể dùng terminal đơn sắc, chế độ tương phản cao hoặc công cụ hỗ trợ truy cập; một số người khó phân biệt đỏ và xanh lá. Vì vậy luôn giữ **chữ level**, **tên event**, **outcome** và **errorCode**. Màu chỉ giúp quét mắt nhanh hơn:

```text
ERROR | event=payment.failed paymentId=pay-42 errorCode=UPSTREAM_TIMEOUT
```

Dòng này vẫn phải hiểu được khi copy sang Slack, CI logs, hệ thống tập trung hoặc in trắng đen. Tránh màu nhấp nháy hoặc phối màu nền/chữ làm mất khả năng đọc.

## 3. TTY, console, pipe, file và CI là những môi trường khác nhau

Khi chạy trực tiếp trong terminal tương tác, màu có thể hữu ích. Nhưng stdout cũng có thể được:

- Chuyển hướng bằng `> application.log` hoặc `2> error.log`.
- Pipe qua `grep`, `awk`, `tee`, `less`, hoặc chương trình parser.
- Thu bởi Docker/Kubernetes hoặc agent đọc stdout/stderr.
- Ghi vào CI/CD job logs với cơ chế hỗ trợ màu khác nhau.
- Hiển thị trong cửa sổ Output của IDE, nơi khả năng ANSI tùy phiên bản và cấu hình.

Nếu chương trình luôn xuất byte màu, file hoặc pipeline có thể nhận thêm `0x1B` và chuỗi `[31m`; trình phân tích dựa vào level ở đầu dòng có thể không nhận ra `ERROR`, còn biểu thức so khớp chính xác có thể thất bại. Với structured JSON logs, mã điều khiển không cần thiết và có thể làm hỏng kỳ vọng của downstream consumer.

**Quy tắc gợi ý cho ứng dụng vận hành:** màu chỉ bật khi đích là terminal có hỗ trợ và người dùng không yêu cầu tắt; khi xuất file, CI hoặc collector, mặc định dùng **plain text** hoặc **structured logging** không màu. Quy tắc này nên được thực hiện bằng config của ứng dụng/backend, không chỉ dựa vào sở thích cá nhân của người viết.

### Kiểm tra terminal trong Java

`System.console() != null` là một **heuristic** cho thấy JVM đang có console tương tác. Nếu stdout bị redirect hoặc chạy qua IDE, giá trị có thể là `null`. Tuy nhiên, nó **không phải phép kiểm tra đầy đủ khả năng hỗ trợ ANSI**: một số terminal tốt vẫn trả `null` trong môi trường launcher/IDE; một số console có mặt nhưng không xử lý được mọi mã màu.

Biến môi trường `TERM` có thể chứa `dumb`, gợi ý môi trường không có khả năng terminal thông thường. `COLORTERM` và nhiều biến khác chỉ là **dấu hiệu**, không phải chuẩn bảo đảm 100% cho một JVM. Với Windows, hành vi còn tùy Windows Terminal, PowerShell, Console Host và chế độ Virtual Terminal Processing; không xem mọi cửa sổ `cmd.exe` là giống nhau.

**Kết luận:** dùng chế độ `auto` làm mặc định hợp lý, đồng thời cho người dùng đặt `always` hoặc `never` rõ ràng.

## 4. Quy ước NO_COLOR và điều khiển màu minh bạch

`NO_COLOR` là quy ước cộng đồng cho công cụ CLI: khi biến môi trường này **tồn tại và không rỗng**, chương trình có màu mặc định nên **không thêm màu**. Ví dụ:

```bash
NO_COLOR=1 java TerminalColorDemo --color=auto
```

Lệnh trên sử dụng cú pháp shell kiểu Bash; trên Windows PowerShell có thể dùng:

```powershell
$env:NO_COLOR = "1"
java TerminalColorDemo --color=auto
```

Lưu ý: đây là **quy ước tự nguyện**, không phải tính năng JVM tự động bật. Nếu code hoặc framework logging không đọc `NO_COLOR` thì biến này **không tự làm màu biến mất**. Bạn cần hỗ trợ trong code hoặc cấu hình runtime tương ứng.

Một giao diện tốt có ba chế độ:

| Chế độ | Khi nào dùng | Ý nghĩa |
| --- | --- | --- |
| `auto` | Mặc định cho CLI | Chỉ tô màu nếu môi trường tương tác có khả năng phù hợp và không có yêu cầu tắt màu. |
| `always` | Người dùng chủ động yêu cầu | Gửi ANSI ngay cả khi stdout bị pipe; có thể dùng khi downstream thực sự hiểu ANSI. |
| `never` | File, CI, collector, machine-readable output | Luôn xuất plain text, tránh mã điều khiển ANSI. |

Khi người dùng **chủ động** yêu cầu `--color=always`, chế độ đó có thể ưu tiên hơn `NO_COLOR` theo quy tắc riêng của ứng dụng. Hãy công bố chính sách rõ. Đừng ép màu khi terminal không hỗ trợ chỉ vì `TERM` chứa chữ `xterm`.

Nguồn tham khảo quy ước: [NO_COLOR – disabling ANSI color output by default](https://no-color.org/).

## 5. Mã ANSI không phải là ký tự hiển thị thông thường

Trong Java:

```java
String label = "\u001B[31mERROR\u001B[0m";
```

`label.length()` **lớn hơn** độ dài chữ `ERROR`, bởi chuỗi bao gồm cả các mã điều khiển. Terminal không dùng các byte đó như ký tự có chiều rộng thông thường, nên căn cột theo `String.length()` có thể bị lệch nếu tính trước hoặc sau khi chèn màu không đúng cách.

Ví dụ:

```text
Thông điệp khi render:
ERROR | event=job.failed

Biểu diễn kiểm tra byte (ký hiệu ESC và LF):
ESC[31mERRORESC[0m | event=job.failedLF
```

Hai biểu diễn không giống nhau ở cấp bytes. Khi cần căn cột, hãy định dạng **phần chữ hiển thị trước**, rồi chèn chuỗi màu quanh nhãn đã được padding. Với Unicode phức tạp, chiều rộng hiển thị còn bị ảnh hưởng bởi ký tự kết hợp, CJK và emoji; `String.length()` không phải hàm đo cột terminal tổng quát.

### Reset không được bỏ quên

Nếu quên `ESC[0m`, các ký tự in sau đó có thể tiếp tục có màu hoặc style cũ. Nếu một exception xuất giữa lúc thêm màu, nên bảo đảm reset ở đường xử lý kết thúc. Với `System.out.println(...)` thông thường, tạo một chuỗi hoàn chỉnh gồm prefix + nội dung + reset sẽ giảm nguy cơ “chảy màu” sang dòng sau.

Dùng `ESC[0m` không giải quyết mọi rủi ro log injection: dữ liệu người dùng có thể chứa chính các mã ESC điều khiển terminal. Hãy xử lý dữ liệu không đáng tin cậy trước khi in ra console; không cho input tùy ý chứa control sequences đi vào terminal quản trị nếu không cần.

## 6. Ví dụ Java 17 hoàn chỉnh: --color=auto/always/never

Chương trình dưới đây là một **minh họa cách trình bày console**, chưa phải một framework logger hoàn chỉnh. Nó dùng JDK 17 thuần, không cần dependency. Các nhãn `INFO`, `WARN` và `ERROR` được tô màu khi bật màu; toàn bộ message được giữ nguyên để có thể tìm kiếm khi tắt màu.

Lưu thành **`TerminalColorDemo.java`**:

```java
public final class TerminalColorDemo {
    private static final String ESC = "\u001B[";
    private static final String RESET = ESC + "0m";

    private static boolean autoColor() {
        String noColor = System.getenv("NO_COLOR");
        String term = System.getenv("TERM");

        boolean noColorRequested =
                noColor != null && !noColor.isEmpty();

        return System.console() != null
                && !noColorRequested
                && !"dumb".equalsIgnoreCase(term);
    }

    private static boolean shouldColor(String mode) {
        return switch (mode) {
            case "--color=always" -> true;
            case "--color=never" -> false;
            case "--color=auto" -> autoColor();
            default -> throw new IllegalArgumentException(
                    "Expected --color=auto, --color=always or --color=never"
            );
        };
    }

    private static void printEvent(
            String level, String eventName, boolean color) {
        String code = switch (level) {
            case "INFO" -> "32";
            case "WARN" -> "33";
            case "ERROR" -> "31";
            default -> "0";
        };

        String label = color
                ? ESC + code + "m" + level + RESET
                : level;

        System.out.println(label + " | event=" + eventName);
    }

    public static void main(String[] args) {
        if (args.length > 1) {
            throw new IllegalArgumentException(
                    "Provide at most one --color option"
            );
        }

        String mode = args.length == 0 ? "--color=auto" : args[0];
        boolean color = shouldColor(mode);

        printEvent("INFO", "service.ready", color);
        printEvent("WARN", "cache.fallback", color);
        printEvent("ERROR", "job.failed", color);
    }
}
```

Biên dịch và chạy bằng **JDK 17 trở lên**:

```bash
javac TerminalColorDemo.java
java TerminalColorDemo --color=never
```

**Standard output chính xác** của lệnh `--color=never`:

```text
INFO | event=service.ready
WARN | event=cache.fallback
ERROR | event=job.failed
```

Mọi dòng đều không có mã ANSI, nên có thể đối chiếu bằng text và chuyển hướng vào file. Thử chế độ màu (terminal có hỗ trợ):

```bash
java TerminalColorDemo --color=always
```

**Kết quả hiển thị:** label INFO xanh lá, WARN vàng, ERROR đỏ; nội dung ` | event=...` vẫn màu mặc định. Byte stream có các chuỗi ANSI:

```text
ESC[32mINFOESC[0m | event=service.ready
ESC[33mWARNESC[0m | event=cache.fallback
ESC[31mERRORESC[0m | event=job.failed
```

**Lưu ý:** ba dòng trên dùng chữ `ESC` để **biểu diễn** ký tự điều khiển, không phải stdout nguyên văn; stdout thực tế chứa byte `0x1B` trước dấu `[`. Màu sẽ không nhất thiết hiển thị đúng trong một công cụ không hỗ trợ ANSI. Với `--color=auto` và đầu ra không có terminal tương tác, ví dụ tự chuyển sang không màu.

### Vì sao code này đáng chú ý?

1. `ESC` dùng mã `\u001B[` của Java; mỗi nhãn level có SGR riêng, reset `0m` đặt ngay sau nhãn.
2. `switch` expression là cú pháp hợp lệ với Java 17; không cần thư viện ngoài JDK.
3. `autoColor()` xem `System.console()`, `NO_COLOR` và `TERM=dumb`. Đây là **heuristic có giới hạn** chứ không phải phát hiện mọi khả năng terminal.
4. `--color=always` là yêu cầu tường minh, có thể xuất mã ANSI khi được pipe sang file; `--color=never` luôn plain text.
5. Giá trị level trong demo chỉ dùng để trình bày, **không thay thế phân loại level, filter, logger hay appender thực tế**.
6. Các event có text cố định nên output `--color=never` không phụ thuộc timestamp, working directory hoặc thread scheduling.

### Kiểm tra redirect

Để đảm bảo file dùng cho collector không chứa ANSI:

```bash
java TerminalColorDemo --color=never > application.log
```

Nội dung file `application.log` là ba dòng plain text như phần stdout chuẩn. Nếu đổi thành `--color=always`, các byte ANSI sẽ được ghi vào file dù có thể không nhìn thấy bằng text editor. Khi cần xác nhận chính xác, dùng công cụ xem hex như `od`/`xxd` trên hệ POSIX hoặc hex viewer phù hợp; không suy đoán từ màu hiển thị của editor.

**Tính di động:** terminal Windows hiện đại có thể hỗ trợ ANSI nhưng khả năng bật Virtual Terminal Processing còn tùy host; terminal legacy hoặc một số ứng dụng/IDE không hỗ trợ. Không có lý do để ép xuất ANSI trong mọi hoàn cảnh.

## 7. Logback: dùng PatternLayout để tô màu level

Trong hệ sinh thái **SLF4J + Logback Classic**, màu thường được cấu hình bằng conversion word trong **PatternLayout**, đưa vào `PatternLayoutEncoder` của `ConsoleAppender`. Tài liệu Logback hỗ trợ `%highlight(...)` và các conversion word như `%red(...)`, `%cyan(...)`, `%yellow(...)`.

Ví dụ file **`src/main/resources/logback.xml`** trong ứng dụng dùng Logback làm backend:

```xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %highlight(%-5level) %cyan(%logger{36}) - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

Trong đó:

- `%d{HH:mm:ss.SSS}` in thời gian; chỉ có giờ địa phương nên không đủ làm timestamp tuyệt đối cho hệ phân tán nếu thiếu timezone.
- `%highlight(%-5level)` tô màu **nhãn level**, căn trái với chiều rộng tối thiểu năm ký tự.
- `%cyan(%logger{36})` tô tên logger cyan và rút gọn khi cần.
- `%msg%n` in message và xuống dòng.
- Appender `CONSOLE` ghi ra `System.out`; chỉ có tác dụng khi Logback là backend đang được chọn và cấu hình đã nạp.

**Màu mặc định của Logback không giống ví dụ Java ở mục 6.** Trong converter `%highlight`, Logback có cách phối màu riêng: ERROR thường bold red, WARN red, INFO blue và một số level khác dùng màu mặc định. Không giả định INFO luôn xanh lá hoặc WARN luôn vàng như bảng gợi ý.

Nếu ứng dụng chạy trong CI, chuyển hướng sang file hoặc log collector không hiểu ANSI, dùng một **cấu hình không màu** cho môi trường đó, chẳng hạn:

```xml
<pattern>%d{HH:mm:ss.SSS} %-5level %logger{36} - %msg%n</pattern>
```

Đây là **một dòng cấu hình thay thế**, không phải nguyên file. Đừng ép appender file nhận các chuỗi màu chỉ vì pattern được sao chép từ console.

### Windows và Jansi

Tài liệu Logback mô tả tùy chọn `<withJansi>true</withJansi>` cho console để hỗ trợ chuyển/loại escape sequences trong một số môi trường, với dependency Jansi phù hợp. **Không thêm `withJansi` chỉ theo thói quen**: yêu cầu, phiên bản và mức hỗ trợ khác nhau giữa các dòng Logback, Jansi, JDK và terminal Windows. Trên nhiều terminal hiện đại, ANSI đã được hỗ trợ trực tiếp. Nếu dùng Jansi, kiểm tra dependency/runtime và output thực tế, đặc biệt khi redirect.

Tài liệu: [Logback Manual – Layouts, Coloring](https://logback.qos.ch/manual/layouts.html).

## 8. Log4j 2: dùng %highlight{...} và tùy chọn ANSI

Trong **Log4j 2 Core**, `PatternLayout` hỗ trợ conversion word `%highlight{pattern}` và `%style{pattern}{style}`, với cú pháp ngoặc nhọn **khác** `%highlight(...)` của Logback.

Ví dụ file **`src/main/resources/log4j2.xml`** trong ứng dụng đang chạy Log4j2 Core:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <Console name="CONSOLE" target="SYSTEM_OUT">
            <PatternLayout
                pattern="%d{HH:mm:ss.SSS} %highlight{%-5level} %logger - %msg%n"
                noConsoleNoAnsi="true"/>
        </Console>
    </Appenders>

    <Loggers>
        <Root level="INFO">
            <AppenderRef ref="CONSOLE"/>
        </Root>
    </Loggers>
</Configuration>
```

Đối với phiên bản Log4j 2 hỗ trợ các thuộc tính này:

- `%highlight{%-5level}` in level với màu phụ thuộc level.
- `noConsoleNoAnsi="true"` tắt xuất mã ANSI nếu `System.console()` là `null`, hữu ích khi output bị pipe hoặc chạy không tương tác. Đây vẫn là heuristic; terminal trong IDE có thể là ngoại lệ.
- `disableAnsi="true"` trên `PatternLayout` là lựa chọn **tắt ANSI không điều kiện** khi cần output không màu, ví dụ cho collector/file.
- `%style{%logger}{cyan}` là ví dụ cách tô một đoạn theo màu xác định.
- Default palette của Log4j2 thường INFO xanh lá, WARN vàng, ERROR đỏ đậm, DEBUG cyan; mapping thực tế có thể thay đổi bằng option của `%highlight`.

Đoạn XML trên minh họa Log4j2, **không dùng nguyên nó cho Logback**. Cũng không trộn `%highlight(%-5level)` của Logback vào Log4j2 vì cú pháp không giống nhau.

Ví dụ cấu hình **chỉ tắt màu** của Log4j2 khi xuất log cho hệ thống khác:

```xml
<PatternLayout pattern="%d{ISO8601} %-5level %logger - %msg%n"
               disableAnsi="true"/>
```

Đây là một **đoạn cấu hình**, cần đặt trong appender hợp lệ. Tài liệu chính thức: [Log4j 2 – Pattern Layout](https://logging.apache.org/log4j/2.x/manual/pattern-layout.html).

## 9. JUL: không có conversion word %highlight mặc định

`java.util.logging` (**JUL**) trong JDK dùng mô hình **Logger → Handler → Formatter**. `ConsoleHandler` và `SimpleFormatter` không cung cấp một conversion word `%highlight` giống Logback/Log4j2. Muốn in ANSI theo level, có thể viết `Formatter` tùy chỉnh, nhưng phải xử lý:

- `LogRecord.getLevel()` cho biết level của record, ví dụ `SEVERE`, `WARNING`, `INFO`, `FINE`.
- `Formatter.formatMessage(record)` để định dạng placeholder `{0}` của JUL trước khi tô màu.
- `LogRecord.getThrown()` để quyết định cách in stack trace/cause; không bỏ mất exception trong log quan trọng.
- Lựa chọn bật màu theo môi trường, thay vì luôn chèn ANSI.
- `Handler` có thể xuất stderr, stdout hoặc file tùy loại; đừng giả định ConsoleHandler mặc định ghi stdout.
- `setUseParentHandlers(false)` khi cần tránh record đến handler cha và gây output lặp không mong muốn.

Đoạn minh họa `Formatter` đơn giản bên dưới chỉ tô **level** và **không in stack trace**; vì vậy **không đủ cho production nếu cần log Throwable**:

```java
// Đoạn minh họa trong code đã có lớp/biến cần thiết.
java.util.logging.Formatter colored = new java.util.logging.Formatter() {
    @Override
    public String format(java.util.logging.LogRecord r) {
        String label = r.getLevel().getName();
        String sgr = r.getLevel().intValue() >=
                java.util.logging.Level.SEVERE.intValue()
                ? "\u001B[31m"
                : "\u001B[0m";
        return sgr + label + "\u001B[0m"
                + " | " + formatMessage(r) + "\n";
    }
};
```

Trong ứng dụng có yêu cầu chuẩn hóa, nên dùng bộ formatter/encoder thích hợp với backend thật thay vì tự nhân bản logic màu ở nhiều chỗ. Nên có chế độ không màu, escape dữ liệu và test điều kiện redirect.

## 10. Màu khi ghi file, structured JSON và hệ thống log tập trung

Trong production, giá trị quan trọng của log thường nằm ở **timestamp**, **level**, **logger/service**, **event**, **requestId/traceId**, **outcome** và **exception**, chứ không phải màu. Bộ thu thập log nên có dữ liệu ổn định để parse và tìm kiếm; mã ANSI có thể làm sai các giả định đó.

Một chính sách phổ biến:

| Đích | Màu ANSI | Dữ liệu nên giữ |
| --- | --- | --- |
| Terminal developer đang tương tác | Có thể bật `auto` | Level, component, message, correlation ID. |
| Console được CI thu thập | Mặc định không màu, trừ khi CI hỗ trợ và người dùng chủ động muốn | Plain text rõ ràng; không phụ thuộc vào màu. |
| File log để grep/parse | Tắt màu | Text ổn định có timestamp và event ID. |
| JSON/NDJSON cho log collector | Tắt ANSI | Trường cấu trúc, timestamp có timezone, requestId/traceId. |
| Trang dashboard quan sát | Màu do **UI** quyết định | Severity dưới dạng field, không phải mã escape từ ứng dụng. |

Khi log đã được structured, dashboard hoàn toàn có thể tô màu WARN/ERROR ở giao diện **dựa trên level field**, không cần ứng dụng nhúng mã màu vào dữ liệu lưu trữ.

### Cách loại escape sequences khỏi log đã có

Với dữ liệu log cũ có mã ANSI, có thể phải lọc khi xem hoặc chuyển dữ liệu. Nhưng regex tự viết để xóa mọi escape sequence có thể thiếu các loại control sequences khác và vô tình sửa dữ liệu, nên **ưu tiên xử lý tại nguồn**: tắt màu ở encoder/appender trước khi đẩy vào collector. Nếu cần làm sạch lịch sử, dùng parser/utility được kiểm chứng trên dữ liệu đại diện và giữ bản gốc để đối chiếu.

### Lưu trữ exception

Stack trace có thể nhiều dòng; một logger/collector nên giữ `Throwable` và cause đúng API. Khi tô màu ERROR, chỉ tô label hoặc đoạn cần thiết, không chèn ANSI vào từng stack frame nếu không cần. Màu không thay thế multiline handling hoặc structured exception fields.

## 11. Những sai lầm phổ biến

| Hiện tượng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| Hiển thị `^[ [31m` hoặc ký tự lạ | Console không hiểu ANSI hoặc log được chuyển hướng. | Tắt màu bằng chế độ never/config plain, kiểm tra terminal support. |
| File `application.log` chứa byte `1B 5B` | Appender/formatter đã nhúng ANSI. | Dùng layout không màu cho file; xác minh bằng hex viewer. |
| Terminal bị đỏ cả phần sau | Quên reset `ESC[0m` hoặc lỗi khi dựng chuỗi. | Reset sau đúng phần tô màu; bảo đảm reset ở đường exception. |
| `--color=auto` không bật màu trong IDE | `System.console()` là `null` dù cửa sổ output hỗ trợ ANSI. | Cho phép tùy chọn always cho môi trường đã kiểm chứng. |
| `NO_COLOR=1` không làm Logback đổi màu | Framework/layout không tự hỗ trợ quy ước này. | Chọn config plain, kiểm tra adapter hoặc logic đọc biến môi trường. |
| Có màu ở stdout nhưng không ở file | Hai appender có pattern/encoder riêng. | Đây có thể là thiết kế đúng; so cấu hình đích. |
| Màu INFO/WARN khác giữa backend | Logback và Log4j2 có palette mặc định khác nhau. | Dùng cấu hình màu rõ ràng hoặc giữ nhãn level để nhất quán. |
| `%highlight` in nguyên chữ | Dùng nhầm syntax/backend hoặc converter không được load. | Kiểm tra cú pháp `%highlight(...)` vs `%highlight{...}` và version. |
| Đếm ký tự căn cột bị lệch | Chuỗi ANSI dài hơn số cột hiển thị. | Padding phần hiển thị trước rồi mới bọc mã màu. |
| CI parser không nhận ra level | Dòng bắt đầu bằng escape code thay vì `ERROR`. | Tắt màu ở nguồn khi xuất đến máy đọc. |
| Log JSON không parse được | Chèn ANSI vào JSON/plain text hoặc tự nối JSON sai. | Dùng structured encoder chuẩn, không có ANSI. |
| Log của người dùng chứa mã điều khiển | Input chưa được sanitize, có thể tạo hiệu ứng terminal ngoài ý muốn. | Escape/loại control characters nguy hiểm trước khi xuất log. |
| Chỉ dựa vào màu để đánh giá lỗi | Terminal theme/khả năng nhìn màu khác nhau. | Giữ level, eventName, outcome, errorCode thành text rõ ràng. |

## 12. Checklist triển khai màu terminal

1. **Nguồn log** đang dùng JUL, Logback, Log4j2 hay thư viện khác? Chọn đúng cách cấu hình cho backend thực tế.
2. **Đích xuất** là terminal tương tác, CI, file, container stdout hay JSON collector? Không đồng nhất chúng.
3. **Mặc định** có ưu tiên no-color khi redirect/pipe không? Có `auto/always/never` hoặc config tương đương?
4. **Tùy chọn người dùng** như `NO_COLOR` (khi non-empty) và cấu hình môi trường được tôn trọng theo chính sách đã công bố?
5. **Cú pháp ANSI** có chứa đúng `ESC[...m` và reset `ESC[0m` không? Có để màu chảy sang message/dòng tiếp theo?
6. **Dễ đọc** khi không màu, màu nền khác, người dùng khó phân biệt màu, hoặc copy qua hệ thống khác?
7. **Formatter/layout** có giữ nguyên logger name, timestamp, message, correlation ID và exception cần thiết?
8. **An toàn dữ liệu**: input người dùng, stack trace, secret và control characters có được xử lý trước khi xuất?
9. **Hiệu năng**: có tạo chuỗi màu/format đắt tiền khi level đã tắt hoặc tải cao không? Đã đánh giá I/O console?
10. **QA**: có thử trực tiếp terminal, redirect `> file`, pipe, CI, IDE, Windows/Linux và `NO_COLOR`?
11. **Collector**: đã xác nhận log máy đọc được không chứa ANSI và không làm sai parse JSON/multiline?
12. **Khả năng vận hành**: dashboard/alert vẫn đánh giá severity bằng field, không phụ thuộc vào màu?

## 13. Tự kiểm tra kiến thức

**Câu 1.** Một event `ERROR` được ghi vào file, thấy chuỗi `[31m` trong file. Cần thay đổi level từ ERROR sang WARN không?

**Đáp án:** Không. Vấn đề thuộc formatter/layout đã thêm ANSI, không phải severity. Dùng layout không màu cho file và giữ đúng level nghiệp vụ.

**Câu 2.** `System.console() == null` có chứng minh terminal không hỗ trợ ANSI không?

**Đáp án:** Không. Đây chỉ là heuristic; IDE hoặc pipeline có thể có cách hiển thị khác. Cho phép người dùng chọn chế độ màu rõ ràng.

**Câu 3.** Khi nào `NO_COLOR=1` có tác dụng?

**Đáp án:** Khi chương trình/framework **hỗ trợ kiểm tra** biến đó hoặc được cấu hình theo ý nghĩa tương đương. JVM không tự tắt mã ANSI trong mọi thư viện.

**Câu 4.** Sự khác nhau giữa `%highlight(%-5level)` và `%highlight{%-5level}`?

**Đáp án:** Dạng ngoặc tròn là conversion word thường gặp trong **Logback**; ngoặc nhọn là dạng **Log4j 2 PatternLayout**. Dùng sai backend có thể không được giải mã như mong muốn.

**Câu 5.** Có nên dùng mã ANSI để tạo cảnh báo trong hệ thống log tập trung không?

**Đáp án:** Không cần. Hệ thống nên dựa trên level và các field/sự kiện; giao diện dashboard tự quyết định màu hiển thị, còn bản ghi lưu trữ giữ định dạng ổn định.

## 14. Tài liệu tham khảo

- [Logback Manual – Layouts: Coloring](https://logback.qos.ch/manual/layouts.html): `%highlight(...)` và các conversion word màu.
- [Apache Log4j 2 – Pattern Layout](https://logging.apache.org/log4j/2.x/manual/pattern-layout.html): `%highlight{...}`, `%style{...}`, `disableAnsi`, `noConsoleNoAnsi`.
- [NO_COLOR – quy ước tắt ANSI color](https://no-color.org/): biến môi trường `NO_COLOR` không rỗng và quyền override tường minh.

**Kết luận:** Màu terminal là tính năng **trình bày** của console logging. Nó làm nhãn INFO/WARN/ERROR dễ nhận ra khi đọc trực tiếp, nhưng không thay thế level, message, trace ID hay thiết kế log an toàn. Chỉ bật ANSI khi đích thật sự thích hợp, luôn có chế độ không màu, reset đúng sau phần được tô và kiểm thử output ở terminal, file, pipe, CI và collector.