# System.in, System.out và System.err trong Java

## 1. Ba luồng I/O chuẩn dùng để làm gì?

Một chương trình dòng lệnh thường có ba kênh giao tiếp với môi trường bên ngoài:

- **`System.in`** là **standard input (stdin)**: luồng byte đầu vào. Nó thường nhận thao tác nhập từ bàn phím khi chương trình chạy trong terminal, nhưng cũng có thể nhận dữ liệu từ tệp, pipe hoặc chương trình khác.
- **`System.out`** là **standard output (stdout)**: luồng đầu ra thông thường, dành cho kết quả mà người dùng hoặc chương trình gọi cần nhận.
- **`System.err`** là **standard error (stderr)**: luồng đầu ra riêng, dành cho lỗi, cảnh báo và thông tin chẩn đoán.

Trong Java, cả ba thuộc lớp `java.lang.System` và có thể truy cập ở bất kỳ đâu bằng `System.in`, `System.out`, `System.err` mà không cần import `System`.

```text
                          ┌───────────────────────────┐
bàn phím / file / pipe ──>│ System.in  : InputStream   │
                          │                           │
                          │        Ứng dụng Java      │
                          │                           │
terminal / file / pipe <──│ System.out : PrintStream   │
terminal / file / pipe <──│ System.err : PrintStream   │
                          └───────────────────────────┘
```

Ba kênh này là **luồng của tiến trình (process)**: khi khởi động chương trình, shell/hệ điều hành thường gắn chúng với terminal; bên gọi có thể đổi hướng luồng mà **không cần sửa mã Java**. Dù stdout và stderr thường cùng hiện trên một màn hình, chúng là **hai kênh logic riêng**. Phân biệt đúng kênh giúp shell lấy kết quả chương trình, lưu lỗi ra tệp và kết nối các chương trình bằng pipe một cách đáng tin cậy.

**Quy tắc giao tiếp đơn giản:** dữ liệu hoặc kết quả chính đi qua `System.out`; lỗi/cảnh báo đi qua `System.err`; chương trình nhận yêu cầu/dữ liệu từ `System.in`. Đây là quy ước thiết kế thường dùng, không phải ràng buộc bắt buộc của Java.

## 2. Kiểu dữ liệu thực tế của ba biến

| Biến | Kiểu Java | Chiều | Thao tác thường dùng |
| --- | --- | --- | --- |
| `System.in` | `java.io.InputStream` | Vào | `read()`, `read(byte[])` |
| `System.out` | `java.io.PrintStream` | Ra | `print()`, `println()`, `printf()`, `write()`, `flush()` |
| `System.err` | `java.io.PrintStream` | Ra | `print()`, `println()`, `printf()`, `write()`, `flush()` |

`InputStream` nhận **byte**; `PrintStream` cũng có khả năng ghi byte, nhưng bổ sung các phương thức thuận tiện để **in văn bản có định dạng**. `PrintStream` triển khai trên `OutputStream`, nên `System.out.write(65)` ghi một byte giá trị 65, còn `System.out.print(65)` ghi văn bản biểu diễn số `65` (thường là hai ký tự). Đây là điểm khác biệt quan trọng khi thiết kế chương trình xuất dữ liệu.

Hai ví dụ sau là các lời gọi **minh họa**, không phải chương trình độc lập:

```java
System.out.write(65);    // Một byte có giá trị 65 (ASCII chữ A).
System.out.print(65);    // Hai ký tự chữ số: 6 và 5.
System.err.println("Không thể mở tệp.");
```

`PrintStream` có các phương thức ghi chuỗi theo encoding được cấu hình. Vì vậy không nên mặc định rằng `System.out` dùng cùng charset với `Charset.defaultCharset()` trên mọi JDK, console và cấu hình. Nếu đầu ra phải là dữ liệu trao đổi theo một định dạng byte chính xác, hãy xác định charset và cách đóng gói dữ liệu trong hợp đồng giao tiếp.

## 3. System.in: đọc stdin dưới dạng byte

Vì `System.in` là `InputStream`, các quy tắc đọc byte vẫn áp dụng:

- `int read()` trả **0 đến 255** khi đọc được một byte, hoặc **-1** khi kết thúc luồng (EOF).
- `int read(byte[] buffer)` trả số byte đọc được; không cam kết luôn điền đầy mảng. Chỉ phần tử từ `0` đến `count - 1` là dữ liệu mới.
- Một lần đọc có thể chờ khi chưa có dữ liệu (blocking). Người dùng chưa nhập phím Enter hoặc phía pipe chưa đưa dữ liệu là những lý do có thể khiến chương trình trông như đang “đứng”.
- EOF không phải ký tự xuống dòng: Enter thường hoàn tất một dòng; EOF có nghĩa nguồn không còn byte.

Nếu nhập **văn bản**, đọc từng byte rồi ép thẳng thành `char` là sai với dữ liệu đa byte như UTF-8. Chọn một charset rõ ràng và dùng `InputStreamReader` để giải mã, có thể thêm `BufferedReader` để đọc theo dòng.

### Khi nào dùng BufferedReader?

`BufferedReader` tiện khi muốn nhận một dòng văn bản. Nó trả `String` không kèm ký tự xuống dòng; trả `null` ở EOF. Nó chấp nhận LF, CR hoặc CRLF để kết thúc dòng.

```java
// Đoạn minh họa; cần import java.io.* và StandardCharsets.
BufferedReader reader = new BufferedReader(
        new InputStreamReader(System.in, StandardCharsets.UTF_8));

String line = reader.readLine();
if (line == null) {
    System.err.println("Không có dữ liệu đầu vào (EOF).");
} else {
    System.out.println("Đã nhập: " + line);
}
```

Đoạn trên **không đóng** `reader` vì wrapper đóng thì `System.in` cũng bị đóng, có thể ảnh hưởng phần khác của ứng dụng tiếp tục đọc stdin. Với một ứng dụng dòng lệnh ngắn và độc lập, việc đóng stdin khi toàn bộ quá trình đã kết thúc có thể chấp nhận được; tuy nhiên ở thư viện, component tái sử dụng, hoặc chương trình nhiều bước, **người sở hữu luồng mới nên quyết định đóng**.

### Ví dụ Java 17 chạy được: đọc một dòng rồi phản hồi

**Tệp `ReadStdin.java`:**

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

public class ReadStdin {
    public static void main(String[] args) throws IOException {
        BufferedReader reader = new BufferedReader(
                new InputStreamReader(System.in, StandardCharsets.UTF_8));

        System.out.print("Name? ");
        System.out.flush(); // Đảm bảo prompt được yêu cầu đẩy ra.

        String name = reader.readLine();
        if (name == null) {
            System.err.println("Input is empty (EOF)");
            return;
        }

        String normalized = name.strip();
        if (normalized.isEmpty()) {
            System.err.println("Input name is blank");
            return;
        }

        System.out.println("Hello, " + normalized);
    }
}
```

Biên dịch bằng JDK 17+:

```bash
javac ReadStdin.java
java ReadStdin
```

Nếu gõ `Lan` và nhấn Enter, terminal thường hiển thị:

```text
Name? Lan
Hello, Lan
```

Dòng `Name? Lan` bao gồm lời nhắc do chương trình in và ký tự người dùng gõ do **terminal echo**. Echo phụ thuộc cách terminal cấu hình, không phải một `println` của Java.

Với stdin đã chứa chính xác một dòng `Lan`, **dữ liệu stdout mà chương trình tạo** là:

```text
Name? Hello, Lan
```

Lúc này dữ liệu được lấy từ nguồn thay vì gõ tương tác; chương trình không in lại chuỗi input đã đọc. **Stderr trống** khi hợp lệ. Nếu stdin có EOF ngay từ đầu, stdout chỉ chứa `Name? ` (không xuống dòng), còn stderr chứa `Input is empty (EOF)` và một newline.

Lệnh chạy với shell hỗ trợ input redirection (Bash hoặc Command Prompt) sau khi tạo tệp văn bản `name.txt` chứa `Lan`:

```bash
java ReadStdin < name.txt
```

Trên **Windows PowerShell 5.1**, cú pháp input redirection `<` không được hỗ trợ giống `cmd.exe`; có thể dùng `cmd /c "java ReadStdin < name.txt"` khi cần giữ cơ chế redirect byte của `cmd`. Nếu dùng pipeline PowerShell như `Get-Content name.txt | java ReadStdin`, việc chuyển dữ liệu qua pipeline có thể ảnh hưởng encoding so với đọc trực tiếp từ tệp; với dữ liệu Unicode cần chọn giải pháp và encoding phù hợp.

### Tại sao phải flush lời nhắc?

`print("Name? ")` không có newline. Một số môi trường có buffering nên prompt có thể chưa xuất hiện trước khi chương trình chờ `readLine()`. `System.out.flush()` là yêu cầu hợp lý tại ranh giới tương tác. Đừng dựa vào việc `println` thường flush tự động ở một số cấu hình như một đảm bảo chung cho mọi output wrapper.

## 4. System.out: đầu ra bình thường và định dạng

`System.out` là `PrintStream`. Các phương thức quen thuộc:

| Phương thức | Công dụng |
| --- | --- |
| `print(value)` | In biểu diễn văn bản của giá trị, **không tự thêm newline** |
| `println(value)` | In giá trị rồi thêm **dấu kết thúc dòng của môi trường** |
| `println()` | Chỉ thêm dòng mới |
| `printf(format, args)` | In theo format string |
| `printf(locale, format, args)` | In theo locale tường minh |
| `format(...)` | Tương tự `printf` |
| `append(...)` | Nối chuỗi ký tự vào `PrintStream` |
| `write(int)`/`write(byte[])` | Ghi byte thô qua tầng output |
| `flush()` | Đẩy dữ liệu đang đệm xuống tầng bên dưới theo khả năng luồng |
| `checkError()` | Kiểm tra trạng thái lỗi ghi của `PrintStream` |

Hàm `println` thêm dòng mới nhưng không bảo đảm byte xuống dòng giống nhau giữa các hệ điều hành: thông thường LF trên Unix và CRLF trên Windows. Để chuẩn hóa một file/protocol cần LF, nên ghi ký tự `"\n"` theo đặc tả thay vì phụ thuộc separator hệ thống.

`printf` sử dụng quy tắc của `java.util.Formatter`:

- `%s`: chuỗi hoặc biểu diễn `String.valueOf(...)`.
- `%d`: số nguyên.
- `%f` và `%.2f`: số thực, với độ chính xác hiển thị.
- `%n`: newline theo môi trường, tốt hơn `"\n"` khi muốn format output theo nền tảng.
- `%%`: dấu phần trăm thực.

Cần chú ý **locale**. Một số locale dùng dấu phẩy làm dấu thập phân, khác dấu chấm. Với kết quả mà máy khác cần parse, nên truyền `Locale.ROOT` hoặc một locale định dạng xác định.

### Ví dụ Java 17: phân biệt print, println và printf

**Tệp `StandardOutputFormat.java`:**

```java
import java.util.Locale;

public class StandardOutputFormat {
    public static void main(String[] args) {
        System.out.print("Items: ");
        System.out.println(3);
        System.out.printf(Locale.ROOT, "Price: %.2f%n", 12.5);
        System.out.println("Done");
    }
}
```

Chạy:

```bash
javac StandardOutputFormat.java
java StandardOutputFormat
```

**Stdout hiển thị** (mỗi dòng kết thúc theo hệ điều hành):

```text
Items: 3
Price: 12.50
Done
```

Nếu bỏ `Locale.ROOT`, kết quả định dạng số thực có thể thay đổi tùy locale mặc định. Khi xuất CSV hoặc dữ liệu máy đọc, việc chỉ định locale thôi cũng chưa đủ để xây dựng định dạng an toàn: cần quy định escaping/quoting, charset và line ending.

### PrintStream và lỗi ghi: điểm dễ bỏ sót

Khác `OutputStream.write(...)` có thể ném `IOException`, các phương thức `PrintStream.print`/`println`/`write` được thiết kế **không ném checked `IOException` trong cách gọi thường lệ**. Chúng ghi nhận lỗi I/O vào trạng thái bên trong; ứng dụng có thể kiểm tra bằng `checkError()`:

```java
// Đoạn minh họa:
System.out.println("result");
System.out.flush();
if (System.out.checkError()) {
    System.err.println("Could not write standard output");
}
```

`checkError()` tự gọi flush nếu stream chưa đóng; trạng thái lỗi thường tồn tại sau khi lỗi ghi xảy ra. **Không coi việc `println` chạy xong là xác nhận bên nhận đã nhận/dùng dữ liệu**. Trong các chương trình xuất dữ liệu quan trọng hoặc pipeline, xem xét chính sách phát hiện broken pipe và exit status phù hợp. Với API không phải `PrintStream`, như `OutputStream` hoặc `Writer` thông thường, lỗi I/O có thể được báo bằng `IOException`.

## 5. System.err: kênh cảnh báo/lỗi độc lập

`System.err` cũng là `PrintStream`, có cùng API `print`, `println`, `printf`. Khác biệt nằm ở **mục đích và kênh tiến trình**: stderr dùng cho chẩn đoán, còn stdout giữ kết quả bình thường.

Một công cụ dòng lệnh có thể xuất kết quả ở stdout để bên gọi đưa tiếp vào chương trình khác, trong khi lỗi/cảnh báo cần được nhìn thấy mà không làm hỏng dữ liệu. Ví dụ, nếu stdout là danh sách ID thuần, việc in `"Warning: ..."` vào stdout có thể khiến chương trình nhận dữ liệu hiểu nhầm đó là một ID. Đưa warning sang stderr giúp dữ liệu stdout dễ parse.

```java
System.out.println("ID-001"); // Kết quả dành cho pipeline.
System.err.println("Warning: using cached data"); // Chẩn đoán.
```

Trên terminal, cả hai dòng có thể cùng hiện ra nên người dùng khó nhận ra kênh. Khi redirect stdout và stderr vào **hai tệp khác nhau**, sự khác biệt trở nên rõ.

### Ví dụ Java 17 chạy được: hai kênh đầu ra

**Tệp `OutputChannels.java`:**

```java
public class OutputChannels {
    public static void main(String[] args) {
        System.out.println("record-1");
        System.err.println("warning: fallback");
        System.out.println("record-2");
    }
}
```

Biên dịch:

```bash
javac OutputChannels.java
```

Ví dụ chạy trên shell hỗ trợ redirection:

```bash
java OutputChannels > result.txt 2> diagnostics.txt
```

**Nội dung `result.txt`:**

```text
record-1
record-2
```

**Nội dung `diagnostics.txt`:**

```text
warning: fallback
```

Đây là ví dụ dễ kiểm chứng rằng stdout và stderr là hai kênh khác nhau. Nếu chỉ chạy `java OutputChannels` và nhìn một terminal chung, **không được dựa vào thứ tự xen kẽ** giữa hai kênh để suy luận thứ tự sự kiện, vì buffering, lịch trình và cơ chế hiển thị có thể khiến các dòng trông khác thứ tự gọi.

## 6. Redirect, pipe và ý nghĩa của 0, 1, 2

Các ký hiệu stdin, stdout và stderr tương ứng theo quy ước hệ điều hành Unix/POSIX với file descriptor **0, 1, 2**. Shell khác nhau có cú pháp redirect tương tự nhưng không hoàn toàn giống nhau. Đối với Bash và Command Prompt, ví dụ thường gặp:

| Cú pháp | Ý nghĩa |
| --- | --- |
| `java App < input.txt` | Lấy stdin từ `input.txt` |
| `java App > output.txt` | Ghi stdout vào tệp, thường **ghi đè** |
| `java App >> output.txt` | Nối thêm stdout vào tệp |
| `java App 2> error.txt` | Ghi stderr vào tệp riêng |
| `java App > output.txt 2> error.txt` | Tách hai đầu ra |
| `java App 2>&1` | Hướng stderr tới nơi stdout hiện đang trỏ |
| `java Producer \| java Consumer` | Nối stdout của Producer với stdin của Consumer |

Khi dùng pipe `Producer | Consumer`, stderr của Producer **thường không tự đi vào stdin của Consumer**; stderr vẫn đi theo tuyến riêng trừ khi có redirection khác. Đây là lý do nên giữ stdout sạch, chỉ chứa dữ liệu mà bên tiêu thụ mong đợi.

**Thứ tự redirect có thể quan trọng.** Chẳng hạn ở Bash, `java App > output.txt 2>&1` cho cả hai kênh cùng ghi tới nơi stdout đã được hướng đến. Còn `java App 2>&1 > output.txt` có ý nghĩa khác vì stderr trước đó được gắn tới đích stdout ban đầu. Khi cùng dồn về một đích, thứ tự các byte/đoạn từ hai luồng không được coi là một thứ tự tổng thể đáng tin cậy chỉ nhờ cú pháp redirect.

**PowerShell có mô hình streams và redirection riêng**, đặc biệt khi gọi native executable qua pipeline, và cách xử lý encoding cũng khác giữa Windows PowerShell 5.1 và PowerShell mới. Hãy thử lệnh trên đúng shell đang sử dụng; không coi mọi cú pháp pipe/redirect là hoàn toàn tương đương về byte, encoding và exit status.

## 7. Stdin và stdout liên quan đến byte và charset như thế nào?

`System.in` đọc byte, còn `BufferedReader(InputStreamReader(...))` đọc text sau khi giải mã. Chọn charset ở biên dữ liệu:

```java
// Mã minh họa; mỗi thư viện có thể chọn charset theo hợp đồng riêng.
BufferedReader reader = new BufferedReader(
        new InputStreamReader(System.in, StandardCharsets.UTF_8));
String text = reader.readLine();
```

Ví dụ giả định dữ liệu được đưa vào stdin là **UTF-8**. Khi dữ liệu thực sự được tạo từ terminal với encoding khác, UTF-8 tường minh có thể không tương thích. Cần xác định nguồn là tệp, pipe, terminal hay hệ thống khác, rồi chọn charset phù hợp. Việc cùng nhìn thấy chữ tiếng Việt trên màn hình không chứng minh các byte trao đổi là UTF-8.

### Console encoding và default charset là hai khái niệm khác

`Charset.defaultCharset()` là charset mặc định cho nhiều API Java; JDK 17 trước JEP 400 có thể phụ thuộc nền tảng, JDK 18+ thường mặc định UTF-8 (với các ngoại lệ/chế độ tương thích). Nhưng charset của **console/standard streams** có thể đi theo cơ chế riêng của JVM và môi trường. Không nên suy luận đơn giản rằng `System.out` luôn là UTF-8 chỉ vì JVM có default charset UTF-8.

Nếu công cụ cần xuất **byte UTF-8 chính xác** để tiêu thụ từ pipe hoặc file, có thể tự tạo `Writer` trên output stream với charset xác định, nhưng phải quản lý việc flush và không tùy tiện đóng standard stream:

```java
// Đoạn minh họa, không phải chương trình độc lập.
Writer utf8 = new OutputStreamWriter(System.out, StandardCharsets.UTF_8);
utf8.write("Xin chào");
utf8.flush();
```

Cần import `java.io.Writer`, `java.io.OutputStreamWriter`, `java.nio.charset.StandardCharsets`, xử lý `IOException`. Không gọi `utf8.close()` giữa vòng đời ứng dụng nếu chương trình còn dùng stdout, vì đóng wrapper sẽ đóng stream bên dưới. Tránh trộn trực tiếp `System.out.print` với việc ghi bằng wrapper có đệm vào cùng một output stream nếu không quản lý thứ tự flush rõ ràng.

Nếu dữ liệu phải là **binary**, dùng byte-oriented API lên output channel hoặc `System.out.write(byte[])` và tách hẳn logging sang `System.err` để không làm hỏng payload.

## 8. System.console() và khác biệt với System.in

`System.console()` trả về một `java.io.Console` khi JVM có console tương tác gắn với quá trình chạy; nó có thể trả **`null`**, thường gặp khi chạy trong IDE, qua một số launcher hoặc với đầu vào/đầu ra đã được redirect.

Khác biệt chính:

- `System.in` luôn là kênh stdin của tiến trình theo API JVM, có thể đọc byte từ pipe/file.
- `Console` cung cấp thao tác đọc dòng, in prompt và `readPassword()` phù hợp hơn cho một số giao diện terminal.
- Khi `System.console() == null`, không được gọi thẳng `console.readLine()`; cần có phương án dùng stdin hoặc thay đổi cách chương trình được chạy.
- `Console.readPassword()` giúp đọc mật khẩu mà không echo theo cách console hỗ trợ; kết quả là `char[]`, có thể xóa sau khi xử lý. Nó **không phải** cách nhập mật khẩu phù hợp khi chương trình đang nhận dữ liệu tự động từ pipe.

### Ví dụ Java 17: nhập qua console hoặc stdin

**Tệp `ConsoleFallback.java`:**

```java
import java.io.BufferedReader;
import java.io.Console;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

public class ConsoleFallback {
    public static void main(String[] args) throws IOException {
        Console console = System.console();
        String name;

        if (console != null) {
            name = console.readLine("Name? ");
        } else {
            BufferedReader reader = new BufferedReader(
                    new InputStreamReader(System.in, StandardCharsets.UTF_8));
            System.out.print("Name? ");
            System.out.flush();
            name = reader.readLine();
        }

        if (name == null) {
            System.err.println("No name (EOF)");
            return;
        }

        System.out.println("Hello, " + name);
    }
}
```

Biên dịch:

```bash
javac ConsoleFallback.java
java ConsoleFallback
```

Với nhập `Minh`, chương trình in lời chào `Hello, Minh` sau khi có một dòng đầu vào; việc prompt hiển thị/echo như thế nào phụ thuộc nhánh console và môi trường. Nếu stdin ở EOF, stderr in `No name (EOF)`. Ví dụ này dùng UTF-8 ở **nhánh fallback**; với môi trường có charset stdin khác, cần điều chỉnh encoding theo dữ liệu thực tế.

Không nên dùng `System.console() != null` làm phép xác minh bảo mật rằng người nhập là người thật, vì chương trình vẫn chịu ảnh hưởng cấu hình terminal và tiến trình bên ngoài.

## 9. Scanner khi nhập dữ liệu có cấu trúc

`java.util.Scanner` là tiện ích cao hơn để phân tích token, số và các kiểu dữ liệu văn bản. Có thể gắn nó với stdin:

```java
// Đoạn minh họa:
Scanner scanner = new Scanner(System.in, StandardCharsets.UTF_8);
String word = scanner.next();
```

Cần import `java.util.Scanner` và `java.nio.charset.StandardCharsets`. Khi sử dụng `nextInt()` rồi `nextLine()`, hãy nhớ `nextInt()` chỉ đọc token số; phần kết thúc dòng vẫn có thể còn trong đầu vào, dẫn đến `nextLine()` trả một chuỗi rỗng. Nếu giao thức dựa trên từng dòng, thường dễ kiểm soát hơn khi dùng `BufferedReader.readLine()` rồi `Integer.parseInt(line.strip())` cùng xử lý lỗi.

`Scanner` cũng có cơ chế `Locale`: parsing dấu phẩy/dấu chấm của số có thể khác nhau giữa các locale. Khi cấu trúc đầu vào có định dạng xác định, cần chọn `scanner.useLocale(Locale.ROOT)` hoặc locale phù hợp với đặc tả.

**Đóng `Scanner` cũng đóng `System.in` bên dưới**, vì thế không tự động `try-with-resources` scanner quanh stdin nếu luồng được dùng chung giữa nhiều đoạn chương trình. Nếu scanner được tạo trên một luồng file mà đoạn mã tự sở hữu, `try-with-resources` vẫn là lựa chọn phù hợp.

## 10. Quản lý vòng đời và không vô tình đóng ba luồng chuẩn

`System.in`, `System.out`, `System.err` thường do JVM/launcher khởi tạo, có vòng đời gắn với cả tiến trình. Đóng trực tiếp chúng có thể khiến những đoạn khác không còn nhập hoặc xuất được.

Ví dụ cần thận trọng:

```java
// Không thích hợp nếu chương trình còn dùng stdout sau khối này.
try (PrintWriter writer = new PrintWriter(System.out)) {
    writer.println("First phase");
}
// PrintWriter.close() đóng luồng System.out bên dưới.
```

Khi tạo wrapper chỉ để dùng trong một phương thức, có thể để luồng chuẩn được quản lý ở cấp ứng dụng và gọi `flush()` khi cần thay vì đóng wrapper giữa chương trình. Với tệp độc lập mà bạn tự mở, vẫn ưu tiên `try-with-resources`. Phân biệt **wrapper** và **quyền sở hữu tài nguyên** là thiết yếu.

`System.out.close()` có thể làm các lần `println` sau không xuất được như mong đợi; `PrintStream` thường ghi nhận lỗi thay vì ném checked `IOException`, nên chương trình có thể “im lặng” mà không thấy exception.

### Khi nào flush?

- **Prompt nhập liệu:** flush trước khi chờ stdin nếu prompt được in mà không có newline.
- **Dữ liệu streaming cần bên nhận xử lý ngay:** flush ở các ranh giới ứng dụng cần, cân bằng hiệu năng.
- **Khi kết thúc quá trình ghi:** flush thông thường là hợp lý; với output stream đã được đóng đúng cách thì close sẽ xử lý buffer tùy implementation.

`flush()` không đảm bảo phía nhận đã đọc dữ liệu, cũng không chứng minh đã ghi bền vững trên ổ đĩa.

## 11. Có thể thay đổi các luồng System bằng setIn, setOut, setErr

Java cung cấp:

```java
System.setIn(InputStream newInput);
System.setOut(PrintStream newOutput);
System.setErr(PrintStream newError);
```

Đây là các lời gọi **minh họa** với biến luồng đã được tạo. Chúng **thay đổi tham chiếu global của JVM** đến standard streams, thường dùng trong test, framework hoặc bootstrap đặc biệt. Khi thay `System.out` bằng một `PrintStream` ghi vào bộ nhớ, code gọi `System.out.println` sau đó được chuyển sang nơi mới; nó không nhất thiết thay đổi file descriptor của mọi thư viện native hoặc tiến trình con.

Vì thay đổi có phạm vi toàn JVM, phải **khôi phục luồng cũ** trong `finally`. Nếu test chạy song song, một test thay `System.out` có thể bắt nhầm output của test khác. Tốt hơn nên thiết kế phần logic quan trọng nhận một `PrintStream`/`Writer` qua tham số khi có thể.

### Ví dụ Java 17 chạy được: tạm thời thu stdout

**Tệp `CaptureStdout.java`:**

```java
import java.io.ByteArrayOutputStream;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;

public class CaptureStdout {
    public static void main(String[] args) {
        PrintStream original = System.out;
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();

        try (PrintStream capture =
                     new PrintStream(bytes, true, StandardCharsets.UTF_8)) {
            System.setOut(capture);
            System.out.print("captured");
        } finally {
            System.setOut(original);
        }

        System.out.println("Captured: "
                + bytes.toString(StandardCharsets.UTF_8));
    }
}
```

Chạy:

```bash
javac CaptureStdout.java
java CaptureStdout
```

**Stdout chính xác:**

```text
Captured: captured
```

Vì `System.out` đã được đổi tạm thời, lần `print("captured")` không đi thẳng ra terminal. Sau khối `finally`, stdout gốc được phục hồi để in kết quả. `capture.close()` chỉ đóng stream tạm, không đóng stdout gốc. Trong ứng dụng đa luồng, ví dụ này cần chạy trong ngữ cảnh kiểm thử được kiểm soát; thao tác thay global stream không phải kỹ thuật an toàn mặc định để thu log từng request.

## 12. stdout/stderr và exit code: hai cơ chế khác nhau

In lỗi ra `System.err` **không tự làm chương trình thất bại**. Ngược lại, một chương trình có thể kết thúc với mã lỗi mà không in gì. Shell và các công cụ automation thường kiểm tra **exit code**, bên cạnh stdout và stderr.

Ví dụ:

```java
// Đoạn minh họa, chỉ gọi khi muốn kết thúc JVM.
System.err.println("Invalid command-line arguments");
System.exit(2);
```

`System.exit(2)` yêu cầu chấm dứt JVM với status 2 theo quy ước ứng dụng; shell thường coi status khác 0 là thất bại. Tránh dùng `System.exit` trong thư viện hoặc unit test vì sẽ kết thúc cả tiến trình chạy. Với phương thức `main` riêng, lựa chọn khác là ném exception chưa bắt hoặc quản lý luồng điều khiển rõ ràng; exit status cụ thể phụ thuộc cách launcher xử lý.

Một CLI tốt thường xác định ba quy ước cùng lúc: **stdout chứa gì**, **stderr chứa gì** và **mã thoát có ý nghĩa gì**. Đối với công cụ chỉ tạo dữ liệu đầu ra, thông báo thành công hoặc progress không nên trộn vào stdout nếu bên gọi cần parse dữ liệu sạch.

## 13. Buffering, trộn hai luồng và tính đồng thời

Dù code lần lượt gọi:

```java
System.out.println("A");
System.err.println("B");
System.out.println("C");
```

điều đó không đảm bảo terminal, IDE hoặc tệp đích hiển thị `A`, `B`, `C` đúng thứ tự nếu hai luồng đi qua **hai cơ chế đệm hoặc tiêu thụ khác nhau**. Flush có thể làm việc xuất hiện kịp thời hơn nhưng không biến hai stream thành một giao thức có thứ tự tổng thể.

Trong chương trình đa luồng, nhiều thread cùng in ra các stream có thể tạo nội dung xen kẽ; ngay cả khi từng lời gọi được đồng bộ ở một mức độ bởi implementation, **đừng dựa vào tính nguyên tử của toàn bộ một thông điệp ứng dụng** nếu ghép từ nhiều lời gọi. Cách tốt hơn là định dạng thông điệp hoàn chỉnh trước khi ghi, hoặc giao việc log theo thứ tự cho một component logging chuyên dụng.

Nếu cả stdout và stderr được redirect chung một tệp, điều này vẫn không tạo một đồng hồ hay một thứ tự sự kiện đáng tin cậy. Để chẩn đoán đa luồng, thường nên có timestamp, thread identifier và cơ chế logging phù hợp thay vì ghép `System.out.println` rải rác.

## 14. Ví dụ thực tế: một CLI có stdout sạch và stderr rõ ràng

Chương trình `NormalizeLines` đọc **từng dòng UTF-8** từ stdin, chuẩn hóa khoảng trắng ở đầu/cuối rồi xuất các dòng không rỗng sang stdout. Thống kê số dòng bị bỏ qua được đưa ra stderr, để có thể pipe stdout vào chương trình khác mà không lẫn thông báo chẩn đoán.

**Tệp `NormalizeLines.java`:**

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.io.Writer;
import java.nio.charset.StandardCharsets;

public class NormalizeLines {
    public static void main(String[] args) throws IOException {
        BufferedReader reader = new BufferedReader(
                new InputStreamReader(System.in, StandardCharsets.UTF_8));
        Writer writer = new OutputStreamWriter(
                System.out, StandardCharsets.UTF_8);

        int omitted = 0;
        String line;

        while ((line = reader.readLine()) != null) {
            String value = line.strip();
            if (value.isEmpty()) {
                omitted++;
                continue;
            }

            writer.write(value);
            writer.write('\n'); // Định dạng đầu ra quy định LF.
        }

        writer.flush(); // Không đóng System.out do ứng dụng còn sở hữu.
        System.err.println("Omitted blank lines: " + omitted);
    }
}
```

Biên dịch:

```bash
javac NormalizeLines.java
```

Giả sử `lines.txt` là một tệp **UTF-8** với nội dung dưới đây (có một dòng chỉ gồm khoảng trắng ở giữa):

```text
  Lan

 Minh
```

Chạy ở Bash/cmd:

```bash
java NormalizeLines < lines.txt > clean.txt 2> stats.txt
```

**Nội dung `clean.txt` đúng theo logic chương trình:**

```text
Lan
Minh
```

**Nội dung `stats.txt`:**

```text
Omitted blank lines: 1
```

`String.strip()` loại khoảng trắng theo định nghĩa Unicode whitespace của Java, khác một số trường hợp so với `trim()`. Chương trình không giữ newline gốc: nó xuất LF cố định, đây là **chủ ý của định dạng đầu ra**. Dòng rỗng có thể là dòng trống thực sự hoặc chỉ chứa whitespace. Trường hợp đầu vào lỗi charset cần được xử lý riêng nếu yêu cầu từ chối UTF-8 không hợp lệ; cấu hình decoder mặc định có thể thay byte lỗi tùy API.

Đây là cách ghép đúng ba kênh: stdin là nguồn dữ liệu, stdout chỉ xuất bản ghi đã xử lý, stderr là thống kê/chẩn đoán. Nếu muốn log/tracing phức tạp hơn, có thể chuyển phần chẩn đoán sang logging framework và cấu hình appender phù hợp.

## 15. Những nhầm lẫn phổ biến

| Nhầm lẫn | Vì sao nguy hiểm | Cách hiểu/sửa |
| --- | --- | --- |
| `System.in` luôn là bàn phím | Stdin có thể là file, pipe hoặc nguồn khác | Thiết kế đọc được cả tương tác và redirect |
| `read()` trả một ký tự văn bản | Nó trả một **byte**, có thể là một phần UTF-8 | Dùng `InputStreamReader` và charset phù hợp cho text |
| `-1` là byte `0xFF` | `read()` trả `int` để phân biệt EOF với 255 | Kiểm tra `int value == -1` |
| `System.out` và `System.err` luôn tương đương | Shell có thể redirect riêng | Kết quả sang stdout; cảnh báo/lỗi sang stderr |
| `print(65)` tương đương `write(65)` | Một bên ghi biểu diễn số, một bên ghi byte | Dùng đúng API text hoặc byte |
| `println` luôn tạo ký tự `'\n'` duy nhất | Separator tùy nền tảng | Chọn `%n` cho dòng hệ thống, `"\n"` cho LF cố định |
| Không có exception nghĩa là `PrintStream` ghi thành công | `PrintStream` có cơ chế lưu trạng thái lỗi | Kiểm tra `checkError()` khi cần |
| Đóng `Scanner(System.in)` chỉ giải phóng Scanner | Nó đóng cả stdin bên dưới | Chỉ đóng khi sở hữu/quyết định kết thúc stdin |
| `System.console()` luôn khác `null` | IDE, pipeline, launcher có thể không cấp Console | Kiểm tra `null`, có nhánh fallback |
| Mọi terminal đều dùng UTF-8 | Encoding có thể tùy cấu hình | Thống nhất charset thực tế hai phía |
| stderr được pipe tự động cùng stdout | Pipe thường chỉ nối stdout | Redirect stderr có chủ đích khi cần |
| Trộn stdout và stderr sẽ giữ đúng thứ tự câu lệnh | Hai stream có buffering/consumer riêng | Đừng dựa vào thứ tự hiển thị |
| `System.setOut` chỉ ảnh hưởng một phương thức | Tham chiếu thay đổi toàn JVM | Khôi phục trong `finally`, tránh test song song |
| In ra stderr tự động trả exit code lỗi | Kênh output và exit status độc lập | Đặt exit status theo giao kèo CLI |

## 16. Chọn công cụ nào cho từng nhu cầu?

- **Nhập một dòng text:** `BufferedReader(new InputStreamReader(System.in, charset))`.
- **Nhập dữ liệu có token/số:** `Scanner` nếu phù hợp, chú ý locale, token còn lại và quyền đóng stdin.
- **Nhập tương tác với prompt/password:** cân nhắc `System.console()` và luôn xử lý `null`.
- **In kết quả thân thiện với người dùng:** `System.out.println` hoặc `printf` với locale xác định nếu cần.
- **In lỗi/cảnh báo:** `System.err`, để stdout giữ dữ liệu đầu ra sạch.
- **Xuất một luồng byte hoặc văn bản theo encoding giao kèo:** dùng byte output hoặc một `Writer` cấu hình charset và định dạng rõ ràng.
- **Kiểm thử output:** ưu tiên truyền `PrintStream`/interface qua dependency injection; chỉ dùng `System.setOut` trong test cô lập và luôn phục hồi luồng gốc.
- **Ứng dụng có logging và chẩn đoán phức tạp:** dùng logging framework thay vì in tự do từ nhiều lớp.

## 17. Bài tập tự kiểm tra

1. Chạy `OutputChannels` ba lần: bình thường, với `> result.txt`, và với `> result.txt 2> diagnostics.txt`. Giải thích thông điệp nào thuộc stdout/stderr.
2. Chạy `ReadStdin` với bàn phím và với tệp input. Quan sát khác biệt giữa **terminal echo** và những byte mà Java thực sự in ra.
3. Thay `System.out.print("Name? ")` bằng `println`, giải thích thay đổi về cách prompt hiển thị và vì sao `flush` vẫn có ý nghĩa trong một số kênh có buffer.
4. Tạo một file UTF-8 gồm tiếng Việt, đọc qua `InputStreamReader(System.in, UTF_8)` và đối chiếu với chạy trong terminal có encoding khác. Ghi lại charset của từng đầu.
5. Dùng `System.err.println` để báo lỗi khi không có input, rồi cho chương trình chạy với stdin EOF. Kiểm tra stdout và stderr độc lập.
6. Mở rộng `NormalizeLines` để nếu toàn bộ input rỗng thì trả exit status 2. Giữ lỗi ở stderr và giải thích vì sao một message trên stderr không đủ để biểu thị thất bại cho script.
7. Viết test cho một phương thức nhận `PrintStream output` rồi gọi `output.println("ok")`. Dùng `ByteArrayOutputStream` để so sánh kết quả mà không thay đổi `System.out` toàn JVM.
8. Tìm và sửa lỗi `Scanner.nextInt()` ngay trước `nextLine()`; đối chiếu với phương án đọc nguyên dòng và parse rõ ràng.
9. Giải thích tại sao stdout là kênh dữ liệu, stderr là kênh chẩn đoán, còn **exit status** là tín hiệu kết quả của tiến trình; ba điều này liên quan nhưng không thay thế nhau.

## 18. Ghi nhớ

`System.in` là **đầu vào kiểu `InputStream`**, còn `System.out` và `System.err` là **hai đầu ra kiểu `PrintStream`**. Chúng là các kênh chuẩn của tiến trình Java và có thể được redirect qua file hoặc pipe. Để viết công cụ dòng lệnh rõ ràng, hãy đọc stdin theo đúng kiểu dữ liệu và charset, xuất kết quả chính ra stdout, đưa lỗi/cảnh báo qua stderr, kiểm soát flush/đóng theo quyền sở hữu, và dùng exit code làm tín hiệu thành công/thất bại cho bên gọi.

### Tài liệu tham khảo

- Java SE 17 API: [`System`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html), [`InputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html), [`PrintStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/PrintStream.html).
- Java SE 17 API: [`Console`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Console.html), [`InputStreamReader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStreamReader.html), [`Scanner`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Scanner.html).
- [JEP 400: UTF-8 by Default](https://openjdk.org/jeps/400) để phân biệt default charset JVM với yêu cầu charset cụ thể ở console/standard streams.
