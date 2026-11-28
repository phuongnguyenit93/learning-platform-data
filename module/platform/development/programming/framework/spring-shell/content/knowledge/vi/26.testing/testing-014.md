# Chuẩn hóa màu ANSI, kích thước màn hình và dữ liệu biến động

Kiểm thử ứng dụng CLI thường gặp một vấn đề: cùng một nội dung có thể được ghi ra terminal theo nhiều cách khác nhau. Terminal có thể thêm mã ANSI để tô màu, di chuyển con trỏ hoặc xóa dòng. Hệ điều hành có thể dùng ký tự xuống dòng khác nhau. Chiều rộng và chiều cao terminal làm bảng bị ngắt dòng hoặc cắt bớt. Ngày giờ, mã định danh, thứ tự dữ liệu và đường dẫn tạm cũng có thể thay đổi giữa các lần chạy.

Nếu so sánh toàn bộ chuỗi output theo từng byte, test dễ thất bại dù nội dung người dùng nhìn thấy vẫn đúng. Ngược lại, nếu chuẩn hóa quá mạnh, test có thể bỏ qua lỗi căn cột, mất màu, sai vị trí hoặc cắt nội dung. Cần chọn mức chuẩn hóa theo điều đang kiểm tra.

Spring Shell 3.3 cung cấp test support với terminal giả lập có kích thước xác định. `@ShellTest` cho phép đặt chiều rộng và chiều cao; `ShellTestClient` chạy command; `ShellScreen.lines()` trả về các dòng đang hiển thị. JLine cung cấp `AttributedString` để phân tích hoặc loại bỏ mã ANSI và đo chiều rộng hiển thị theo cột.

Sau bài này, bạn có thể:

- Phân biệt nội dung văn bản, style ANSI và lệnh điều khiển màn hình.
- Chuẩn hóa ANSI và newline khi test nội dung thuần.
- Giữ lại thông tin bố cục khi test bảng và căn cột.
- Cấu hình terminal giả lập với chiều rộng và chiều cao cố định.
- Kiểm thử output ở màn hình hẹp, rộng và thấp.
- Đo chiều rộng Unicode theo số cột hiển thị.
- Cố định thời gian, ID, thứ tự dữ liệu, locale và đường dẫn.
- Tránh test bất ổn do tác vụ bất đồng bộ và snapshot quá chi tiết.

> Ví dụ dùng Spring Shell 3.3.x, JLine 3.x, JUnit Jupiter và AssertJ. Các API `@ShellTest.terminalWidth`, `terminalHeight` và `ShellScreen.lines()` được minh họa theo Javadoc Spring Shell 3.3.0.

## 1. Vì sao output CLI dễ thay đổi giữa các lần chạy?

Một command có thể trả về nội dung:

~~~text
Đơn hàng 1024 đã được tạo.
~~~

Nhưng chuỗi được ghi ra terminal có thể chứa thêm mã màu:

~~~text
\u001B[32mĐơn hàng 1024 đã được tạo.\u001B[0m
~~~

Trên terminal, người dùng chỉ thấy câu thông báo màu xanh. Trong dữ liệu test, chuỗi còn chứa các ký tự điều khiển bắt đầu bằng ESC. Nếu test so sánh với chuỗi không màu, phép so sánh byte-for-byte sẽ thất bại.

Ngoài ANSI, output còn chịu ảnh hưởng bởi:

| Nguồn biến động | Biểu hiện trong test |
|---|---|
| Mã màu ANSI | Chuỗi có ESC, CSI và mã reset style |
| Điều khiển con trỏ | Chuỗi có lệnh di chuyển cursor, xóa dòng hoặc xóa màn hình |
| Hệ điều hành | `\n` và `\r\n` khác nhau |
| Kích thước terminal | Bảng xuống dòng, cột bị rút gọn hoặc danh sách bị cắt |
| Unicode | Một ký tự có thể chiếm một hoặc hai cột hiển thị |
| Thời gian | Timestamp thay đổi ở mỗi lần chạy |
| ID ngẫu nhiên | UUID hoặc mã tham chiếu không ổn định |
| Thứ tự collection | Dòng output có thể đổi vị trí |
| Locale/timezone | Ngày, giờ, dấu thập phân và tên tháng thay đổi |
| Đường dẫn/môi trường | Thư mục tạm hoặc biến môi trường khác nhau |
| Bất đồng bộ | Test đọc màn hình trước khi output cuối cùng xuất hiện |

Mục tiêu là làm cho test chỉ nhạy với khác biệt có ý nghĩa. Test nội dung không nên phụ thuộc mã màu; test màu phải kiểm tra style; test bố cục phải giữ khoảng trắng và kích thước màn hình.

~~~mermaid
flowchart TD
    A[Raw terminal output] --> B{Đang kiểm tra điều gì?}
    B -->|Nội dung| C[Loại ANSI và chuẩn hóa newline]
    B -->|Màu sắc| D[Parse thành AttributedString]
    B -->|Bố cục / tương tác| E[Đọc visible screen từ emulator]
    C --> F[Assert text và dữ liệu ổn định]
    D --> G[Assert text và style]
    E --> H[Assert dòng, cột, width và height]
~~~

## 2. Phân biệt ANSI style với điều khiển màn hình

ANSI không chỉ dùng để tô màu. Có thể chia các chuỗi điều khiển thành hai nhóm:

- **Style (SGR):** đổi màu chữ, màu nền, đậm, nghiêng, gạch chân hoặc reset style.
- **Điều khiển terminal:** di chuyển con trỏ, xóa dòng/màn hình, cuộn, đổi chế độ hiển thị hoặc chuyển sang alternate screen.

Ví dụ SGR:

~~~text
ESC[31m       Đổi màu chữ sang đỏ
ESC[1m        Bật chữ đậm
ESC[0m        Reset style
~~~

Ví dụ điều khiển vị trí:

~~~text
ESC[2K        Xóa dòng hiện tại
ESC[1A        Di chuyển con trỏ lên một dòng
ESC[2J        Xóa màn hình
~~~

Khi kiểm tra nội dung văn bản cuối cùng, có thể loại bỏ ANSI rồi so sánh text. Khi kiểm tra màn hình tương tác, không nên chỉ xóa mọi escape sequence khỏi raw output: lệnh di chuyển con trỏ và xóa dòng có ý nghĩa đối với cách màn hình được dựng. Hãy kiểm tra màn hình đã được terminal emulator xử lý, chẳng hạn `ShellScreen.lines()`.

## 3. Chuẩn hóa ANSI bằng JLine

JLine có `AttributedString.stripAnsi(String)` để loại bỏ ANSI escape sequence khỏi chuỗi và trả về văn bản thuần. Đây là cách phù hợp hơn việc tự viết một regex đơn giản chỉ tìm mã màu `ESC[...m`, vì output có thể chứa nhiều dạng ANSI khác nhau.

Ví dụ:

~~~java
import org.jline.utils.AttributedString;

String raw = "\u001B[32mĐã lưu thành công\u001B[0m";
String plain = AttributedString.stripAnsi(raw);
~~~

Sau khi chuẩn hóa, `plain` có nội dung:

~~~text
Đã lưu thành công
~~~

Có thể tạo helper cho test:

~~~java
import org.jline.utils.AttributedString;

final class TerminalOutputNormalizer {

    private TerminalOutputNormalizer() {
    }

    static String stripAnsi(String output) {
        return AttributedString.stripAnsi(output);
    }
}
~~~

Test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class TerminalOutputNormalizerTest {

    @Test
    void removesAnsiStyleSequences() {
        String raw = "\u001B[31mERROR\u001B[0m: dữ liệu không hợp lệ";

        assertThat(TerminalOutputNormalizer.stripAnsi(raw))
                .isEqualTo("ERROR: dữ liệu không hợp lệ");
    }
}
~~~

Không nên dùng helper này để kiểm tra raw output của một màn hình full-screen. Khi ứng dụng dùng cursor movement hoặc redraw, hãy lấy các dòng hiển thị từ screen emulator và kiểm tra kết quả sau khi các lệnh điều khiển đã được áp dụng.

### Khi cần giữ style để kiểm tra màu

`AttributedString.fromAnsi(String)` phân tích chuỗi ANSI thành một `AttributedString`, trong đó văn bản và style được giữ riêng. `toString()` trả về nội dung văn bản; `styleAt(index)` cho phép đọc style tại vị trí ký tự.

~~~java
import org.jline.utils.AttributedString;

String raw = "\u001B[1;31mERROR\u001B[0m: không thể lưu";
AttributedString styled = AttributedString.fromAnsi(raw);

String text = styled.toString();
int columns = styled.columnLength();
~~~

Hãy tách hai mục tiêu kiểm tra:

- Kiểm tra nội dung: xác nhận `text` có thông báo đúng.
- Kiểm tra style: xác nhận style của đoạn `ERROR` có màu/thuộc tính theo thiết kế.

Không nên so sánh toàn bộ chuỗi ANSI byte-for-byte. Terminal có thể biểu diễn cùng một style bằng mã khác nhau, hoặc không hỗ trợ đầy đủ màu 256/true color. Nếu màu là yêu cầu sản phẩm, hãy kiểm tra thuộc tính style đã phân tích, không khóa test vào một chuỗi escape cụ thể.

## 4. Chuẩn hóa newline và khoảng trắng

Windows thường dùng `\r\n`; Unix-like thường dùng `\n`. Một số output cũ hoặc terminal control có thể dùng `\r` để quay về đầu dòng. Khi test nội dung văn bản, chuẩn hóa newline trước khi so sánh:

~~~java
static String normalizeNewlines(String text) {
    return text
            .replace("\r\n", "\n")
            .replace('\r', '\n');
}
~~~

Nếu khoảng trắng cuối dòng không mang ý nghĩa, có thể bỏ chúng khi so sánh nội dung:

~~~java
import java.util.Arrays;
import java.util.List;

static List<String> normalizeContentLines(String raw) {
    String text = AttributedString.stripAnsi(raw)
            .replace("\r\n", "\n")
            .replace('\r', '\n');

    return Arrays.stream(text.split("\n", -1))
            .map(line -> line.replaceAll("[ \\t]+$", ""))
            .toList();
}
~~~

Tuy nhiên, không áp dụng right-trim cho mọi test. Với bảng có cột cố định, khoảng trắng đệm là một phần của bố cục. Nếu xóa hết khoảng trắng cuối dòng, test có thể bỏ qua lỗi chiều rộng hoặc căn cột. Nên có hai cách đọc:

| Mục tiêu | Cách chuẩn hóa |
|---|---|
| Kiểm tra nội dung câu chữ | Loại ANSI, chuẩn hóa newline, có thể bỏ khoảng trắng cuối dòng |
| Kiểm tra căn cột/bảng | Giữ khoảng trắng, giữ từng dòng và đo chiều rộng hiển thị |
| Kiểm tra full-screen redraw | Đọc screen sau khi terminal emulator xử lý control sequence |
| Kiểm tra màu | Phân tích ANSI thành attributed text và kiểm tra style riêng |

Không gộp nhiều dòng thành một chuỗi bằng cách xóa toàn bộ whitespace. Việc đó có thể làm một bảng lệch cột vẫn vượt qua test.

## 5. Đặt kích thước terminal cố định với @ShellTest

Spring Shell 3.3 test support giả lập terminal với kích thước mặc định rộng 80 cột và cao 24 dòng. Có thể đặt kích thước khác bằng hai thuộc tính:

- `spring.shell.test.terminal-width`
- `spring.shell.test.terminal-height`

Hoặc đặt trực tiếp trên `@ShellTest`:

~~~java
@ShellTest(terminalWidth = 120, terminalHeight = 40)
class WideTerminalTest {
}
~~~

Ví dụ test cho terminal hẹp:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.shell.test.ShellTestClient;
import org.springframework.shell.test.autoconfigure.ShellTest;
import org.springframework.test.context.ContextConfiguration;

@ShellTest(terminalWidth = 40, terminalHeight = 12)
@ContextConfiguration(classes = OrdersShellTestApplication.class)
class NarrowTerminalTest {

    @Autowired
    ShellTestClient client;

    @Test
    void rendersOrdersWithinTheConfiguredWidth() {
        var session = client.nonInterative("orders list").run();
        List<String> lines = session.screen().lines();

        assertThat(lines).isNotEmpty();
        assertThat(lines).allSatisfy(line ->
                assertThat(new AttributedString(line).columnLength())
                        .isLessThanOrEqualTo(40));
    }
}
~~~

Ví dụ minh họa cách đặt width/height và đọc màn hình cuối. `OrdersShellTestApplication` là cấu hình test chứa command và các dependency cần thiết. Test này phù hợp với output dạng dòng; nếu ứng dụng chủ động cho phép bảng tràn hoặc cuộn ngang, hãy kiểm tra hành vi đó theo contract thay vì bắt mọi dòng phải vừa màn hình.

### Kiểm tra nhiều kích thước

Tạo các test class hoặc test context có kích thước riêng:

~~~java
@ShellTest(terminalWidth = 40, terminalHeight = 12)
@ContextConfiguration(classes = OrdersShellTestApplication.class)
class CompactTerminalTest {
    // Kiểm tra wrap, rút gọn cột hoặc phân trang.
}
~~~

~~~java
@ShellTest(terminalWidth = 120, terminalHeight = 40)
@ContextConfiguration(classes = OrdersShellTestApplication.class)
class WideTerminalTest {
    // Kiểm tra bảng nhiều cột và nội dung đầy đủ.
}
~~~

Khi test dùng kích thước terminal khác nhau, để mỗi cấu hình có test context rõ ràng. Không thay đổi kích thước dùng chung giữa các test đang chạy song song vì kết quả có thể phụ thuộc thứ tự thực thi hoặc context cache.

## 6. Kiểm thử chiều rộng và chiều cao riêng biệt

Chiều rộng và chiều cao ảnh hưởng đến hai hành vi khác nhau:

- **Width:** quyết định số cột có thể hiển thị, điểm wrap, cắt gọn và cách chia layout.
- **Height:** quyết định số dòng nhìn thấy, vùng cuộn, phân trang hoặc nội dung bị khuất.

Ví dụ ma trận kiểm thử:

| Kích thước | Tình huống nên kiểm tra |
|---|---|
| 40 × 12 | Terminal hẹp và thấp; kiểm tra wrap, rút gọn và nội dung quan trọng |
| 80 × 24 | Kích thước mặc định; kiểm tra bố cục phổ biến |
| 120 × 40 | Terminal rộng và cao; kiểm tra bảng nhiều cột |
| 60 × 8 | Terminal có ít dòng; kiểm tra phân trang, cuộn hoặc thông báo |

Không cần kiểm thử mọi tổ hợp có thể. Chọn kích thước đại diện cho các breakpoint trong ứng dụng, cộng với một trường hợp ngay dưới hoặc trên breakpoint quan trọng.

### Width test nên kiểm tra điều gì?

- Header không chồng lên dữ liệu.
- Cột quan trọng vẫn xuất hiện.
- Mô tả được wrap hoặc truncate theo quy tắc.
- Bảng không vượt quá chiều rộng khi ứng dụng cam kết vừa màn hình.
- Không có từ hoặc mã định danh bị cắt sai nếu giá trị cần giữ nguyên.

### Height test nên kiểm tra điều gì?

- Header hoặc prompt quan trọng vẫn nhìn thấy.
- Dòng cuối không ghi đè status bar.
- Danh sách dài có chỉ báo trang hoặc cuộn phù hợp.
- Nội dung bị khuất có thể truy cập theo thao tác đã thiết kế.
- Dialog không vượt quá vùng hiển thị mà không có cách đóng.

Không chỉ kiểm tra `lines().size()` bằng một số cố định nếu shell có prompt, status hoặc dòng trống phụ thuộc trạng thái. Hãy xác nhận các vùng và thông tin có ý nghĩa.

## 7. Đo chiều rộng hiển thị thay vì String.length()

`String.length()` đếm đơn vị UTF-16, không phải số cột mà terminal dùng. Một ký tự tiếng Việt có dấu kết hợp có thể gồm nhiều code point; ký tự Đông Á thường chiếm hai cột; emoji có thể gồm nhiều code point nhưng hiển thị như một grapheme.

JLine có `AttributedString.columnLength()` để tính độ rộng hiển thị theo cột. Ví dụ:

~~~java
import org.jline.utils.AttributedString;

String label = "Khách hàng Nguyễn An";
int displayColumns = new AttributedString(label).columnLength();
~~~

Khi test dòng hiển thị:

~~~java
assertThat(new AttributedString(line).columnLength())
        .isLessThanOrEqualTo(40);
~~~

Phép đo này hữu ích hơn `line.length() <= 40` khi output có tiếng Việt, ký tự Đông Á hoặc emoji. Đối với grapheme cluster phức tạp, kết quả còn phụ thuộc khả năng terminal và cấu hình JLine; nếu ứng dụng cần hỗ trợ terminal cụ thể, hãy kiểm tra trên emulator và terminal mục tiêu.

## 8. Cố định thời gian bằng Clock

Không gọi `LocalDateTime.now()` hoặc `Instant.now()` trực tiếp trong logic cần kiểm thử nếu thời gian là một phần của output. Inject `Clock` để test có thể cố định thời điểm:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;

public class ReportService {

    private final Clock clock;

    public ReportService(Clock clock) {
        this.clock = clock;
    }

    public String generatedAt() {
        return Instant.now(clock).toString();
    }
}
~~~

Trong test:

~~~java
Clock fixedClock = Clock.fixed(
        Instant.parse("2026-10-15T08:30:00Z"),
        ZoneId.of("UTC"));

ReportService service = new ReportService(fixedClock);

assertThat(service.generatedAt())
        .isEqualTo("2026-10-15T08:30:00Z");
~~~

Nếu command hiển thị ngày theo timezone của người dùng, inject `Clock` hoặc `ZoneId` đã được cấu hình rõ ràng. Không phụ thuộc timezone mặc định của máy chạy test.

## 9. Cố định ID, random và thứ tự dữ liệu

UUID, số ngẫu nhiên và thứ tự collection có thể làm snapshot thay đổi ở mỗi lần chạy.

### ID sinh tự động

Đưa bộ sinh ID thành dependency:

~~~java
import java.util.UUID;
import java.util.function.Supplier;

public class ExportJobService {

    private final Supplier<UUID> idGenerator;

    public ExportJobService(Supplier<UUID> idGenerator) {
        this.idGenerator = idGenerator;
    }

    public UUID createJobId() {
        return idGenerator.get();
    }
}
~~~

Trong test, truyền một giá trị cố định:

~~~java
UUID fixedId = UUID.fromString(
        "123e4567-e89b-12d3-a456-426614174000");

ExportJobService service = new ExportJobService(() -> fixedId);

assertThat(service.createJobId()).isEqualTo(fixedId);
~~~

Không cần mock một random generator phức tạp nếu chỉ cần cung cấp một supplier trả về giá trị cố định.

### Thứ tự danh sách

Nếu output cần thứ tự ổn định, service hoặc renderer nên sắp xếp theo một khóa rõ ràng:

~~~java
List<OrderSummary> ordered = orders.stream()
        .sorted(Comparator.comparing(OrderSummary::orderNumber))
        .toList();
~~~

Đừng dựa vào thứ tự duyệt `HashMap` hoặc một collection không cam kết thứ tự. Nếu thứ tự là một phần của nghiệp vụ, hãy test quy tắc sắp xếp đó. Nếu thứ tự không quan trọng, so sánh tập hợp hoặc các dòng sau khi chuẩn hóa thứ tự thay vì snapshot chuỗi cố định.

## 10. Cố định locale, timezone, path và environment

Các giá trị sau thường làm output khác nhau giữa máy phát triển và CI:

| Giá trị | Cách làm ổn định |
|---|---|
| Ngày/giờ | Inject `Clock` và `ZoneId` |
| Định dạng số/ngày | Truyền `Locale` rõ ràng cho formatter |
| Đường dẫn tạm | Dùng `@TempDir`, thay prefix biến động bằng placeholder khi so sánh |
| Environment variable | Inject configuration object hoặc đặt property riêng trong test |
| Working directory | Truyền thư mục rõ ràng, không dựa vào current directory |
| Thứ tự dữ liệu | Sort theo khóa ổn định hoặc so sánh như collection |

Ví dụ formatter:

~~~java
DateTimeFormatter formatter =
        DateTimeFormatter.ofPattern("dd/MM/uuuu", Locale.forLanguageTag("vi-VN"))
                .withZone(ZoneId.of("UTC"));
~~~

Nếu test chỉ quan tâm nội dung báo cáo, có thể thay đường dẫn tạm bằng placeholder:

~~~java
String normalized = output
        .replace(temporaryDirectory.toString(), "<tmp>")
        .replace('\\', '/');
~~~

Chỉ thay đường dẫn khi vị trí file không phải điều đang kiểm tra. Nếu test cần xác nhận service ghi đúng thư mục, phải giữ và kiểm tra path thật.

## 11. Chờ output bất đồng bộ theo điều kiện

Một số thao tác shell có thể phát sinh output sau khi command bắt đầu, ví dụ tiến độ, tác vụ nền hoặc cập nhật trạng thái. Không giả định output cuối đã xuất hiện ngay sau một lần gửi input.

Tránh dùng `Thread.sleep(...)` với thời gian cố định. Test có thể chạy chậm trên CI và nhanh trên máy cá nhân, khiến sleep vừa lãng phí vừa không bảo đảm điều kiện đã hoàn tất.

Với interactive session, chờ tới khi màn hình có nội dung mong đợi bằng một điều kiện có giới hạn thời gian:

~~~java
await()
        .atMost(Duration.ofSeconds(2))
        .untilAsserted(() ->
                ShellAssertions.assertThat(session.screen())
                        .containsText("Hoàn tất"));
~~~

Thời gian chờ phải có giới hạn để test thất bại rõ ràng khi ứng dụng không cập nhật. Nếu có thể, hãy chờ trạng thái nghiệp vụ hoặc completion signal thay vì chỉ đợi một chuỗi xuất hiện.

## 12. Snapshot output: khi nào nên dùng?

Snapshot hữu ích để phát hiện thay đổi bố cục hoặc nội dung, nhưng dễ trở nên mong manh nếu lưu cả raw ANSI, timestamp, UUID và khoảng trắng không quan trọng.

Trước khi so sánh snapshot:

1. Chọn đúng nguồn: raw output, plain text hay visible screen lines.
2. Loại ANSI style nếu snapshot chỉ quan tâm nội dung.
3. Chuẩn hóa newline.
4. Cố định clock, ID, locale và thứ tự dữ liệu.
5. Thay các path tạm bằng placeholder nếu chúng không thuộc contract.
6. Giữ nguyên khoảng trắng nếu snapshot đang kiểm tra căn cột.
7. Chỉ cập nhật snapshot khi thay đổi giao diện đã được xem xét có chủ đích.

Ví dụ snapshot nội dung:

~~~java
String actual = normalizeContentLines(rawOutput).stream()
        .collect(Collectors.joining("\n"));

assertThat(actual).isEqualTo("""
        Đơn hàng 1024
        Trạng thái: OPEN
        Tổng tiền: 22.50
        """.stripTrailing());
~~~

Với bảng hoặc màn hình có layout, nên snapshot theo từng dòng visible screen và giữ khoảng trắng. Có thể bổ sung assertion cấu trúc như tiêu đề, cột bắt buộc và chiều rộng để test giải thích rõ điều gì sai.

Không tạo một snapshot riêng cho mọi terminal và mọi hệ điều hành. Hãy kiểm thử các breakpoint đại diện và những hành vi quan trọng; dùng test thực tế trên terminal mục tiêu cho các khác biệt mà emulator không mô phỏng được.

## 13. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Test sai dù nội dung nhìn giống nhau | Output có ANSI escape sequence | Dùng `AttributedString.stripAnsi` khi kiểm tra plain text |
| Test sai trên Windows nhưng đúng trên Linux | Newline khác nhau | Chuẩn hóa `\r\n` và `\n` |
| Bảng bị lệch nhưng test vẫn pass | Đã trim toàn bộ khoảng trắng cuối dòng | Giữ whitespace trong test layout |
| Test width pass dù terminal quá hẹp | Dùng `String.length()` với Unicode | Đo bằng `AttributedString.columnLength()` |
| Bảng wrap khác nhau giữa test và runtime | Test dùng width mặc định nhưng người dùng có terminal khác | Đặt `terminalWidth` đại diện và kiểm thử breakpoint |
| Dòng cuối bị mất trong test | Chiều cao terminal thấp hoặc screen chỉ giữ vùng nhìn thấy | Kiểm tra pagination/scroll và các dòng visible |
| Test màu phụ thuộc máy | So sánh mã ANSI thô hoặc palette cụ thể | Phân tích style và kiểm tra thuộc tính cần thiết |
| Test full-screen thất bại sau khi strip ANSI | Đã loại bỏ cả lệnh cursor movement | Kiểm tra `ShellScreen.lines()` sau khi emulator xử lý |
| Snapshot thay đổi mỗi lần chạy | Timestamp, UUID hoặc random value | Inject Clock và ID generator cố định |
| Dòng bảng đổi thứ tự | Collection không có thứ tự xác định | Sort theo khóa hoặc so sánh collection không thứ tự |
| Ngày tháng khác trên CI | Locale hoặc timezone mặc định khác | Đặt Locale và ZoneId rõ ràng |
| Test thỉnh thoảng không thấy output cuối | Đọc screen trước khi tác vụ bất đồng bộ hoàn tất | Chờ điều kiện có timeout, tránh `Thread.sleep` |
| Snapshot chứa thư mục máy phát triển | Path tạm hoặc working directory được ghi trực tiếp | Dùng `@TempDir` và placeholder có kiểm soát |

## 14. Checklist chuẩn hóa output

- Xác định test đang kiểm tra nội dung, style, bố cục hay tương tác terminal.
- Dùng `AttributedString.stripAnsi` cho assertion plain text.
- Dùng `AttributedString.fromAnsi` nếu cần kiểm tra style.
- Không strip control sequence khi test full-screen redraw; đọc visible screen sau emulator.
- Chuẩn hóa newline giữa các hệ điều hành.
- Chỉ trim whitespace khi khoảng trắng cuối dòng không có ý nghĩa.
- Đặt `terminalWidth` và `terminalHeight` rõ ràng trong `@ShellTest`.
- Kiểm thử màn hình hẹp, mặc định và rộng theo breakpoint của ứng dụng.
- Dùng `columnLength()` để đo Unicode display width.
- Cố định thời gian, ID, random, locale, timezone và thứ tự dữ liệu.
- Dùng `@TempDir` và placeholder cho path chỉ khi path không thuộc contract.
- Chờ output bất đồng bộ bằng điều kiện có timeout.
- Giữ snapshot tập trung vào hành vi người dùng cần thấy.
- Chạy một số kiểm thử thủ công trên terminal mục tiêu khi cần xác nhận màu, font, Unicode hoặc key handling.

## 15. Bài tập thực hành

Tạo test cho command `orders list` hiển thị bảng đơn hàng:

1. Dùng `@ShellTest` với terminal 80 × 24 và lấy output qua `ShellTestClient`.
2. Viết helper loại ANSI bằng `AttributedString.stripAnsi`.
3. Chuẩn hóa newline và kiểm tra nội dung header, mã đơn hàng, trạng thái.
4. Viết test riêng giữ khoảng trắng để kiểm tra căn cột.
5. Tạo test context với width 40 và height 12; xác nhận mô tả được wrap hoặc rút gọn theo quy tắc.
6. Tạo test context với width 120 và height 40; xác nhận cột bổ sung xuất hiện khi đủ chỗ.
7. Dùng `AttributedString.columnLength()` để kiểm tra dòng có tiếng Việt và emoji.
8. Nếu command hiển thị timestamp, inject `Clock.fixed(...)` và xác nhận output ổn định.
9. Nếu đơn hàng có ID sinh tự động, inject supplier trả về UUID cố định.
10. Sắp xếp dữ liệu theo mã đơn hàng trước khi render và kiểm tra thứ tự.
11. Thêm test cho màu: kiểm tra text độc lập với ANSI, rồi kiểm tra style ở test riêng.
12. Nếu có progress output bất đồng bộ, chờ thông báo hoàn tất bằng điều kiện có timeout.
13. Chạy test trên Windows và Linux CI; chỉ chuẩn hóa khác biệt không thuộc contract.

Khi hoàn thành, hãy giải thích vì sao test plain text có thể bỏ mã màu, trong khi test bảng phải giữ khoảng trắng và test full-screen cần đọc màn hình sau khi terminal emulator xử lý các lệnh điều khiển.

## Tài liệu tham khảo

- [Spring Shell 3.3 – Testing](https://docs.spring.io/spring-shell/docs/3.3.0/docs/): test support, shell sessions và cấu hình terminal giả lập.
- [Spring Shell 3.3 – ShellTest API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/test/autoconfigure/ShellTest.html): `terminalWidth`, `terminalHeight` và kích thước mặc định 80 × 24.
- [Spring Shell 3.3 – ShellScreen API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/test/ShellScreen.html): đọc các dòng đang hiển thị qua `lines()`.
- [Spring Shell 3.3 – ShellTestClient API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/test/ShellTestClient.html): chạy interactive/non-interactive session và đọc screen.
- [JLine 3 – Attributed Strings](https://jline.org/versions/3.x/docs/advanced/attributed-strings/): biểu diễn text có style, màu và thuộc tính.
- [JLine – AttributedString API](https://javadoc.io/doc/org.jline/jline-terminal/latest/org/jline/utils/AttributedString.html): `fromAnsi`, `stripAnsi`, `styleAt` và thao tác với attributed text.
- [JLine – AttributedCharSequence API](https://javadoc.io/doc/org.jline/jline-terminal/latest/org/jline/utils/AttributedCharSequence.html): đo chiều rộng hiển thị bằng `columnLength()`.
- [JUnit 5 – User Guide](https://junit.org/junit5/docs/current/user-guide/): test lifecycle, parameterized tests và extension model.
