# Kiểm tra UTF-8 mặc định, locale, timezone và hành vi môi trường

Khi chuyển một ứng dụng lên Java 21, cần kiểm tra những giá trị mặc định mà JVM nhận từ hệ điều hành và môi trường triển khai. Các khác biệt thường gây lỗi không nằm ở cú pháp Java mà ở cách ứng dụng đọc/ghi văn bản, định dạng số và ngày tháng, diễn giải thời gian, xử lý đường dẫn hoặc phụ thuộc biến môi trường.

Java 21 dùng UTF-8 làm default charset theo JEP 400, áp dụng từ JDK 18. Đây là thay đổi quan trọng với ứng dụng nâng cấp từ JDK cũ từng dựa vào charset mặc định theo máy. Locale và timezone vẫn phụ thuộc môi trường hoặc cấu hình JVM; chúng không tự trở thành giá trị cố định chỉ vì ứng dụng chạy trên Java 21.

## 1. Các nhóm mặc định cần kiểm tra

| Nhóm | API/nguồn quan sát | Rủi ro khi nâng cấp hoặc đổi môi trường |
|---|---|---|
| Default charset | `Charset.defaultCharset()` | Dữ liệu cũ được ghi bằng charset hệ điều hành có thể bị đọc sai nếu code dựa vào charset mặc định |
| Console charset | `Console.charset()` khi có console | Charset terminal có thể khác default charset; ký tự hiển thị sai dù file UTF-8 đúng |
| Locale | `Locale.getDefault()` và locale category `FORMAT`, `DISPLAY` | Dấu thập phân, tiền tệ, tên tháng, cách sắp xếp và chữ hoa/thường có thể khác |
| Timezone | `ZoneId.systemDefault()` | Ngày giờ và thời điểm chuyển DST khác giữa máy developer, CI và production |
| Hệ điều hành | `os.name`, `os.arch`, `file.separator`, `line.separator` | Đường dẫn, phân biệt chữ hoa/thường, newline và quyền file khác nhau |
| System properties | `user.language`, `user.country`, `user.timezone`, `user.dir`, `java.io.tmpdir` | Giá trị mặc định có thể khác theo container, service account hoặc tham số JVM |
| Environment variables | `System.getenv(...)` | Biến cấu hình có thể thiếu, khác tên hoặc khác giá trị giữa môi trường |

Không nên coi giá trị đọc được từ máy developer là cấu hình chuẩn cho production. Hãy xác định giá trị nào cần được cố định theo hợp đồng ứng dụng và giá trị nào được phép phụ thuộc người dùng hoặc môi trường.

## 2. UTF-8 là default charset từ Java 18

JEP 400 thay đổi default charset của Java thành UTF-8 trên các nền tảng được hỗ trợ, bắt đầu từ JDK 18. Do đó, trên Java 21:

```java
import java.nio.charset.Charset;

System.out.println(Charset.defaultCharset()); // UTF-8
```

Các API dùng default charset sẽ sử dụng UTF-8 theo mặc định, ví dụ:

- `new String(bytes)` và `someString.getBytes()`.
- `new InputStreamReader(inputStream)` và `new OutputStreamWriter(outputStream)` nếu không truyền charset.
- Một số constructor của `FileReader` và `FileWriter` không nhận `Charset`.

Không phải mọi API văn bản đều dựa vào default charset. Ví dụ `Files.readString(path)` và `Files.writeString(path, text)` dùng UTF-8 theo hợp đồng API. Hãy đọc Javadoc của từng API thay vì suy luận từ `Charset.defaultCharset()`.

### Vì sao ứng dụng cũ có thể bị lỗi?

Trước Java 18, default charset thường phụ thuộc hệ điều hành và cấu hình máy. Một ứng dụng cũ có thể đã đọc file Windows-1252 hoặc một charset legacy khác bằng `new FileReader(file)` mà không khai báo encoding. Sau khi nâng lên Java 21, cùng đoạn code có thể diễn giải các byte đó như UTF-8, dẫn đến `MalformedInputException`, ký tự thay thế hoặc mojibake.

Ví dụ: file được tạo bởi hệ thống cũ vẫn giữ encoding cũ; nâng JDK không tự chuyển đổi byte trong file sang UTF-8. Cần xác định encoding thật của dữ liệu nguồn.

## 3. Khai báo charset tường minh cho file và network

Với file và giao thức trao đổi dữ liệu, nên chỉ rõ charset để hành vi ổn định trên mọi runtime:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

static void writeUtf8(Path path, String content) throws Exception {
    Files.writeString(path, content, StandardCharsets.UTF_8);
}

static String readUtf8(Path path) throws Exception {
    return Files.readString(path, StandardCharsets.UTF_8);
}
```

Khi dùng stream:

```java
import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

static void readUtf8Stream(InputStream input) throws Exception {
    try (BufferedReader reader = new BufferedReader(
            new InputStreamReader(input, StandardCharsets.UTF_8))) {
        String line;
        while ((line = reader.readLine()) != null) {
            process(line);
        }
    }
}
```

Đối với HTTP hoặc protocol khác, charset phải tuân theo content type và hợp đồng giao thức. Không mặc định mọi response đều là UTF-8 nếu server không cam kết điều đó; kiểm tra header và đặc tả API.

### Chuyển đổi file legacy sang UTF-8

Khi file cũ được xác nhận là Windows-1252, có thể đọc bằng charset nguồn rồi ghi ra một file UTF-8 mới:

```java
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

static void convertLegacyFile(Path source, Path destination)
        throws Exception {
    Charset sourceCharset = Charset.forName("windows-1252");
    String content = Files.readString(source, sourceCharset);
    Files.writeString(destination, content, StandardCharsets.UTF_8);
}
```

`windows-1252` chỉ là ví dụ. Phải xác minh charset thực tế từ hệ thống tạo file hoặc metadata; không đoán encoding dựa trên vài ký tự hiển thị. Giữ file nguồn, kiểm tra nội dung sau chuyển đổi và chỉ thay thế dữ liệu cũ sau khi có kế hoạch rollback.

## 4. Default charset khác console charset

Default charset không nhất thiết là charset của terminal. JEP 400 giữ riêng quy tắc console I/O để tương thích với môi trường console. Trên Java 21, có thể xem charset của console qua `Console.charset()` khi JVM có console:

```java
import java.io.Console;
import java.nio.charset.Charset;

System.out.println("Default charset: " + Charset.defaultCharset());

Console console = System.console();
if (console != null) {
    System.out.println("Console charset: " + console.charset());
} else {
    System.out.println("No interactive console is attached");
}
```

`System.console()` có thể trả về `null` khi ứng dụng chạy trong IDE, service, container hoặc khi input/output được redirect. Không dùng kết quả này để suy ra charset của file hoặc network stream.

Khi ghi file log hoặc file trao đổi, tạo writer với `StandardCharsets.UTF_8`. Khi giao tiếp với terminal, kiểm tra encoding terminal và cách launcher cấu hình standard streams.

## 5. Các thuộc tính charset cần biết khi chẩn đoán

Có thể ghi nhận một số thuộc tính JVM trong diagnostic report:

```java
import java.nio.charset.Charset;

System.out.println("default charset = " + Charset.defaultCharset());
System.out.println("file.encoding = " + System.getProperty("file.encoding"));
System.out.println("native.encoding = " + System.getProperty("native.encoding"));
```

`file.encoding` phản ánh cấu hình default charset của runtime. `native.encoding` cung cấp thông tin encoding native của môi trường trên các JDK hỗ trợ thuộc tính này; nó hữu ích cho chẩn đoán, không phải lựa chọn thay thế cho charset tường minh.

Không thay đổi `file.encoding` bằng `System.setProperty()` sau khi JVM đã khởi tạo và mong rằng các API đã cache default charset sẽ đổi theo. Trên JDK 18+, JEP 400 quy định UTF-8 là mặc định; `-Dfile.encoding=COMPAT` có thể được dùng như biện pháp chuyển tiếp để tái hiện hành vi default charset tương thích nền tảng cũ, nhưng không nên dùng làm cấu hình lâu dài cho dữ liệu trao đổi.

## 6. Locale: FORMAT và DISPLAY

Locale mô tả quy ước ngôn ngữ và vùng miền. Java phân biệt hai nhóm mặc định thường gặp:

- `Locale.Category.FORMAT`: định dạng số, tiền tệ, ngày tháng và dữ liệu tương tự.
- `Locale.Category.DISPLAY`: ngôn ngữ dùng để hiển thị tên locale, tên quốc gia, tên ngôn ngữ và thông tin giao diện.

Đọc cả hai giá trị thay vì chỉ đọc một locale chung:

```java
import java.util.Locale;

System.out.println("Default locale: " + Locale.getDefault());
System.out.println("Format locale: "
        + Locale.getDefault(Locale.Category.FORMAT));
System.out.println("Display locale: "
        + Locale.getDefault(Locale.Category.DISPLAY));
```

Locale mặc định thường được khởi tạo từ cấu hình hệ điều hành và có thể bị ảnh hưởng bởi system properties như `user.language` và `user.country`. Trong container hoặc môi trường CI, các giá trị này có thể khác máy phát triển.

## 7. Locale data có thể thay đổi kết quả định dạng

JDK 9 chuyển sang CLDR làm nguồn dữ liệu locale mặc định theo JEP 252. Các bản JDK và bản cập nhật CLDR có thể cập nhật ký hiệu tiền tệ, tên tháng, cách viết ngày, quy tắc collation và dữ liệu ngôn ngữ.

Do đó, cùng một lời gọi formatter có thể cho kết quả khác sau khi nâng JDK hoặc đổi locale mặc định. Điều này thường không phải lỗi tính toán, mà là thay đổi dữ liệu locale hoặc cấu hình môi trường.

Ví dụ định dạng tiền tệ theo locale cụ thể:

```java
import java.text.NumberFormat;
import java.util.Locale;

NumberFormat vietnameseCurrency =
        NumberFormat.getCurrencyInstance(Locale.forLanguageTag("vi-VN"));

System.out.println(vietnameseCurrency.format(1234567.89));
```

Khi định dạng nội dung cho người dùng, truyền locale của người dùng một cách tường minh. Khi tạo dữ liệu máy đọc, dùng định dạng chuẩn không phụ thuộc locale, chẳng hạn ISO-8601 cho thời gian và định dạng số được quy định bởi protocol.

### Tránh phụ thuộc locale mặc định cho identifier

`String.toLowerCase()` và `String.toUpperCase()` không truyền locale sẽ dùng default locale. Kết quả có thể khác giữa các vùng, ví dụ quy tắc chữ `I` trong tiếng Thổ Nhĩ Kỳ.

Với identifier kỹ thuật, key không phụ thuộc ngôn ngữ, tên protocol hoặc token chuẩn hóa, dùng `Locale.ROOT`:

```java
import java.util.Locale;

String normalized = externalCode.toUpperCase(Locale.ROOT);
```

Với văn bản hiển thị cho người dùng, hãy dùng locale phù hợp với ngôn ngữ của người dùng thay vì `Locale.ROOT`.

Không gọi `Locale.setDefault()` tùy tiện trong thư viện hoặc trong từng request. Đây là trạng thái toàn JVM và có thể làm các request chạy đồng thời ảnh hưởng lẫn nhau. Ưu tiên truyền `Locale` vào formatter hoặc API cần nó.

## 8. Timezone mặc định và ZoneId

`ZoneId.systemDefault()` trả về timezone mặc định mà JVM đang sử dụng. Giá trị này có thể phụ thuộc cấu hình hệ điều hành, container hoặc system property `user.timezone`.

```java
import java.time.ZoneId;

System.out.println("System zone: " + ZoneId.systemDefault());
System.out.println("Configured timezone: "
        + System.getProperty("user.timezone"));
```

Không giả định mọi máy chủ đều chạy UTC hoặc cùng timezone. Máy developer, CI, container và production có thể có timezone mặc định khác nhau. Nếu ứng dụng cần UTC, hãy dùng `ZoneOffset.UTC` hoặc `ZoneId.of("UTC")` một cách tường minh.

Có thể cấu hình timezone của JVM khi khởi chạy:

```bash
java -Duser.timezone=UTC -jar app.jar
```

Tham số này đặt default timezone của tiến trình. Với nghiệp vụ cần timezone riêng theo tenant hoặc người dùng, truyền `ZoneId` theo request; đừng thay đổi timezone mặc định toàn JVM trong lúc ứng dụng đang phục vụ nhiều request.

## 9. Instant, LocalDateTime và ZonedDateTime

Khi nâng cấp hoặc chuẩn hóa xử lý thời gian, cần chọn đúng kiểu dữ liệu:

| Kiểu | Ý nghĩa | Dùng khi |
|---|---|---|
| `Instant` | Một thời điểm tuyệt đối trên timeline UTC | Timestamp sự kiện, thời điểm tạo/cập nhật dữ liệu |
| `LocalDate` | Ngày lịch không kèm giờ và timezone | Ngày sinh, ngày nghỉ, ngày hóa đơn nếu nghiệp vụ chỉ quan tâm ngày |
| `LocalDateTime` | Ngày và giờ trên đồng hồ địa phương, không xác định được instant nếu thiếu zone/offset | Lịch hẹn hoặc thời gian địa phương cần ghép với zone riêng |
| `OffsetDateTime` | Ngày giờ kèm UTC offset | Trao đổi timestamp có offset rõ ràng |
| `ZonedDateTime` | Ngày giờ gắn với vùng timezone và quy tắc của vùng đó | Lịch theo vùng như `Asia/Ho_Chi_Minh` hoặc `Europe/Paris` |

Không lưu `LocalDateTime` như thể nó luôn là một timestamp UTC. Nếu cần một thời điểm duy nhất, dùng `Instant`; nếu cần giữ ý nghĩa giờ địa phương, lưu thêm `ZoneId` hoặc thông tin offset theo yêu cầu nghiệp vụ.

## 10. DST và thay đổi timezone database

Các vùng timezone có thể áp dụng daylight saving time (DST) hoặc thay đổi quy tắc theo quyết định pháp lý. Một giờ địa phương có thể không tồn tại trong ngày chuyển sang giờ mùa hè (gap), hoặc xuất hiện hai lần khi quay lại giờ chuẩn (overlap).

Java lấy dữ liệu timezone từ tzdb được đóng gói trong runtime. Bản cập nhật JDK có thể cập nhật quy tắc timezone; do đó, lịch tương lai ở một khu vực có thể được diễn giải khác sau khi tzdb được cập nhật.

Ví dụ dùng timezone vùng cụ thể:

```java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;

ZoneId paris = ZoneId.of("Europe/Paris");
LocalDateTime localAppointment = LocalDateTime.of(2026, 10, 25, 2, 30);
ZonedDateTime appointment = localAppointment.atZone(paris);

System.out.println(appointment);
```

Ví dụ trên nằm trong khoảng thời gian DST có thể tạo overlap ở Paris. `atZone` áp dụng quy tắc mặc định của `ZoneRules` để giải quyết local time không đơn trị; với overlap, nó mặc định chọn offset sớm hơn. Có thể kiểm tra `paris.getRules().getValidOffsets(localAppointment)`: danh sách rỗng biểu thị gap, hai offset biểu thị overlap và một offset biểu thị thời gian không mơ hồ. Nếu nghiệp vụ cần chọn offset sớm/muộn cụ thể, hãy xử lý các trường hợp này có chủ đích.

Không hard-code offset cố định như `+01:00` cho một vùng có DST nếu ý nghĩa nghiệp vụ là giờ địa phương của vùng đó. Dùng region ID như `Europe/Paris` để JVM áp dụng quy tắc tzdb.

## 11. Làm cho test thời gian và locale có tính xác định

Test không nên phụ thuộc timezone hiện tại của máy chạy test hoặc đồng hồ thực. Dùng `Clock` để truyền thời gian vào logic:

```java
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;

Clock fixedClock = Clock.fixed(
        Instant.parse("2026-11-16T10:00:00Z"),
        ZoneOffset.UTC);

LocalDate today = LocalDate.now(fixedClock);
```

Trong ứng dụng, nhận `Clock` qua constructor hoặc tham số để test có thể dùng `Clock.fixed(...)`. Không gọi `ZoneId.systemDefault()` ở nhiều nơi trong logic nghiệp vụ nếu timezone phải được kiểm soát.

Với formatter, truyền locale và timezone/zone rõ ràng:

```java
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

DateTimeFormatter formatter = DateTimeFormatter
        .ofPattern("dd MMM uuuu HH:mm", Locale.forLanguageTag("vi-VN"))
        .withZone(ZoneId.of("Asia/Ho_Chi_Minh"));
```

Test nên bao phủ các trường hợp biên có ý nghĩa: cuối năm, đầu năm, ngày nhuận, DST gap/overlap của vùng có DST, locale khác nhau và dữ liệu Unicode có dấu.

## 12. Các mặc định môi trường khác ngoài charset/locale/timezone

Ngoài ba nhóm chính, quá trình migration cần xem xét một số khác biệt hệ điều hành và runtime:

| Thành phần | Cách kiểm tra | Khuyến nghị |
|---|---|---|
| OS và kiến trúc | `os.name`, `os.version`, `os.arch` | Không giả định mọi môi trường chạy cùng hệ điều hành hoặc kiến trúc |
| Path separator | `file.separator`, `path.separator` | Dùng `Path`, `Paths` và `Path.resolve()` thay vì nối chuỗi đường dẫn |
| Line separator | `System.lineSeparator()` | Chỉ dùng newline nền tảng khi định dạng cho phép; protocol phải tuân theo newline của đặc tả |
| Working directory | `user.dir` | Dùng đường dẫn cấu hình rõ ràng; không giả định process luôn chạy từ thư mục project |
| Temporary directory | `java.io.tmpdir` | Dùng `Files.createTempFile()` và dọn file theo vòng đời |
| Environment variables | `System.getenv("NAME")` | Xác thực giá trị bắt buộc, đặt default có chủ đích và không dump toàn bộ environment vào log |

Không tạo đường dẫn bằng cách ghép `"/"` hoặc `"\"` thủ công. Dùng `Path.of(base).resolve(child)` để Java xử lý separator phù hợp với hệ điều hành.

`System.lineSeparator()` phản ánh newline nền tảng. Tuy nhiên, định dạng trao đổi có quy tắc riêng: HTTP/1.1 dùng CRLF cho dòng giao thức; một số file chuẩn yêu cầu LF. Không thay newline theo hệ điều hành nếu điều đó làm sai protocol.

## 13. Diagnostic snapshot khi khởi động ứng dụng

Có thể ghi nhận các giá trị môi trường quan trọng một lần lúc startup để hỗ trợ so sánh giữa developer, CI và production. Không ghi secret hoặc dump toàn bộ environment:

```java
import java.io.Console;
import java.nio.charset.Charset;
import java.time.ZoneId;
import java.util.Locale;

public final class RuntimeEnvironmentReport {
    public static void print() {
        Console console = System.console();

        System.out.println("java.version = "
                + System.getProperty("java.version"));
        System.out.println("os.name = "
                + System.getProperty("os.name"));
        System.out.println("os.arch = "
                + System.getProperty("os.arch"));
        System.out.println("default.charset = " + Charset.defaultCharset());
        System.out.println("console.charset = "
                + (console == null ? "(no console)" : console.charset()));
        System.out.println("locale.format = "
                + Locale.getDefault(Locale.Category.FORMAT));
        System.out.println("locale.display = "
                + Locale.getDefault(Locale.Category.DISPLAY));
        System.out.println("timezone.default = " + ZoneId.systemDefault());
        System.out.println("user.dir = "
                + System.getProperty("user.dir"));
        System.out.println("java.io.tmpdir = "
                + System.getProperty("java.io.tmpdir"));
        System.out.println("line.separator = "
                + System.lineSeparator()
                        .replace("\r", "\\r")
                        .replace("\n", "\\n"));
    }
}
```

Báo cáo này nên được ghi trong log startup có kiểm soát. Khi so sánh môi trường, lưu thêm cấu hình JVM, container image, JDK vendor/update và các biến cấu hình ứng dụng cần thiết; không ghi access token, password hoặc giá trị bí mật.

## 14. Cấu hình mặc định qua JVM properties

Một số system properties có thể được truyền khi khởi chạy JVM:

```bash
java \
  -Duser.timezone=UTC \
  -Duser.language=en \
  -Duser.country=US \
  -jar app.jar
```

Đây là ví dụ cố định default timezone và locale của tiến trình. Với ứng dụng đa người dùng, thường tốt hơn khi truyền `Locale` và `ZoneId` theo từng nghiệp vụ thay vì đổi default toàn tiến trình.

Không đặt `file.encoding` thành một giá trị tùy ý để ép encoding từng API. Trên Java 21, UTF-8 đã là default charset; các API trao đổi dữ liệu vẫn nên nhận charset tường minh. `-Dfile.encoding=COMPAT` chỉ nên dùng tạm thời để điều tra tương thích với ứng dụng cũ, không thay cho việc chuyển đổi dữ liệu và sửa code.

## 15. Checklist migration lên Java 21

1. Ghi nhận `Charset.defaultCharset()`, console charset, locale FORMAT/DISPLAY và `ZoneId.systemDefault()` trên môi trường cũ và Java 21.
2. Tìm các lời gọi dùng charset ngầm như `new String(bytes)`, `getBytes()`, `InputStreamReader` hoặc `FileReader` không truyền charset.
3. Xác định encoding thật của dữ liệu file cũ; chuyển đổi có kiểm chứng sang UTF-8 nếu cần.
4. Chuẩn hóa file, network payload và protocol bằng charset tường minh.
5. Kiểm tra format số, tiền tệ, ngày tháng, collation và case conversion với locale cụ thể.
6. Tìm logic phụ thuộc `Locale.getDefault()` hoặc `Locale.setDefault()`; tránh thay đổi global locale trong lúc phục vụ request.
7. Kiểm tra timezone mặc định trên developer, CI, container và production; xác định timezone nghiệp vụ rõ ràng.
8. Thay các phép tính thời gian phụ thuộc đồng hồ thật bằng `Clock` có thể inject trong test.
9. Kiểm thử DST gap/overlap, ngày nhuận và các timestamp biên theo vùng timezone có liên quan.
10. Kiểm tra path, line ending, working directory, temporary directory và biến môi trường trên mọi hệ điều hành triển khai.
11. Ghi diagnostic snapshot khi startup để phát hiện môi trường sai cấu hình sớm.
12. Chạy regression test với dữ liệu Unicode, locale và timezone đại diện trước khi phát hành.

## 16. Các lỗi migration thường gặp

- **File cũ bị đọc sai sau nâng JDK:** code dùng default charset nhưng dữ liệu được tạo bằng charset nền tảng cũ. Xác định encoding nguồn và chuyển đổi dữ liệu có kiểm soát.
- **Console hiển thị sai nhưng file đúng:** console charset khác UTF-8. Kiểm tra `Console.charset()` và terminal/launcher.
- **Số tiền hoặc ngày tháng đổi định dạng:** locale mặc định hoặc locale data thay đổi. Truyền locale tường minh và dùng định dạng máy đọc cho protocol.
- **Timestamp lệch giờ:** timezone mặc định của container hoặc máy chủ khác môi trường trước đó. Dùng `Instant` cho thời điểm tuyệt đối và `ZoneId` cho giờ địa phương.
- **Lịch hẹn lệch một giờ:** code dùng offset cố định hoặc không xử lý DST gap/overlap. Dùng region timezone và kiểm tra `ZoneRules`.
- **Test chạy khác nhau trên CI:** test phụ thuộc locale/timezone/clock của máy. Dùng locale, zone và `Clock` cố định.
- **Đường dẫn hoạt động trên Windows nhưng lỗi trên Linux:** nối chuỗi separator hoặc giả định filesystem không phân biệt hoa/thường. Dùng `Path` và kiểm tra tên file.
- **Protocol hỏng do newline:** dùng `System.lineSeparator()` thay cho newline được đặc tả yêu cầu. Tuân theo định dạng giao thức.

## 17. Biên dịch và chạy với Java 21

Các API `Charset`, `Locale`, `ZoneId`, `Clock`, `Files` và `Console.charset()` có thể dùng trực tiếp với Java 21; không cần bật Preview.

```bash
javac --release 21 -d out src/RuntimeEnvironmentReport.java
java -cp out RuntimeEnvironmentReport
```

`--release 21` đặt mức ngôn ngữ và API khi biên dịch. Hành vi mặc định lúc chạy vẫn phụ thuộc JDK runtime, system properties, cấu hình hệ điều hành và môi trường container.

## 18. Tài liệu tham khảo

- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400)
- [JEP 252 — Use CLDR Locale Data by Default](https://openjdk.org/jeps/252)
- [Java SE 21 API — Charset](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/Charset.html)
- [Java SE 21 API — Console](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/Console.html)
- [Java SE 21 API — Locale](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.html)
- [Java SE 21 API — ZoneId](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/ZoneId.html)
- [Java SE 21 API — Clock](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Clock.html)
- [Java SE 21 API — Files](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html)
