# Kiểm thử EOF, dữ liệu rỗng và thao tác bị gián đoạn với Java Console

## 1. Tại sao đây là các trường hợp khác nhau?

Ứng dụng Java chạy trong terminal thường gọi `java.io.Console.readLine(...)` để hỏi và đọc một dòng; nếu không có console, nó có thể đọc `System.in` qua `BufferedReader`. Tuy cùng phục vụ đầu vào dạng dòng, chúng phải được kiểm thử với **những trạng thái độc lập**:

1. Người dùng nhập dữ liệu hợp lệ.
2. Người dùng nhấn Enter mà không gõ ký tự nào.
3. Người dùng chỉ gõ khoảng trắng hoặc tab.
4. Luồng input đã đến **EOF (end of file/end of stream)**.
5. Dòng cuối có ký tự nhưng **không có dấu xuống dòng** trước EOF.
6. Lỗi I/O thật, hoặc thao tác đọc bị gián đoạn trong một triển khai I/O có hỗ trợ báo lỗi đó.
7. Một phép đọc bị **kẹt/chặn** và test hoặc ứng dụng muốn hủy vì timeout.

Cần phân biệt đặc biệt: **`null` không giống `""`; một phép đọc bị chặn không giống EOF; `Thread.interrupt()` không bảo đảm mọi lời gọi đọc console đều được hủy.**

Bài dùng API còn hợp lệ trong **Java 17+**, ưu tiên kiểm thử thuần Java với đầu vào có thể kiểm soát, kèm integration test cho console/pipe thật. Không giả định các cách khởi chạy Java đều có `Console`.

## 2. Hợp đồng trả về của `readLine()`

Với `Console`:

~~~java
Console console = System.console();
if (console == null) {
    throw new IllegalStateException("Không có console tương tác.");
}

String value = console.readLine("Nhập một dòng: ");
if (value == null) {
    System.out.println("EOF");
} else if (value.isEmpty()) {
    System.out.println("Dòng rỗng");
} else if (value.isBlank()) {
    System.out.println("Chỉ có khoảng trắng");
} else {
    System.out.println("Có dữ liệu: " + value);
}
~~~

Đây là **đoạn minh họa** bên trong method, có `import java.io.Console;`; nó không phải file chạy độc lập. `System.console()` có thể trả `null` nếu môi trường khởi động không có console phù hợp. `Console.readLine("...")` in prompt và đọc một dòng, bỏ ký tự xuống dòng ở cuối. `readLine()` không có argument sẽ đọc **không tự in prompt**.

Với input từ file hoặc pipeline:

~~~java
BufferedReader reader = new BufferedReader(
        new InputStreamReader(System.in, StandardCharsets.UTF_8));
String value = reader.readLine();
~~~

Đây là **đoạn ghép vào method** có import `java.io.BufferedReader`, `java.io.InputStreamReader`, `java.nio.charset.StandardCharsets` và khai báo/khống chế `IOException`. `BufferedReader.readLine()` đọc đến `\n`, `\r`, `\r\n` hoặc EOF. Đó là cơ chế chủ chốt để tạo unit test ổn định.

### Ma trận kết quả

| Input được cấp cho lần đọc | Giá trị trả về | Ý nghĩa cần kiểm tra |
| --- | --- | --- |
| `"An\n"` | `"An"` | Dữ liệu bình thường; không gồm newline |
| `"\n"` | `""` | Dòng rỗng: có line terminator, nhưng không có nội dung |
| `"   \t\n"` | `"   \t"` | Dòng không rỗng nhưng chỉ gồm whitespace; `isBlank() == true` |
| `""` (luồng trống và kết thúc ngay) | `null` | EOF trước khi đọc ký tự nào |
| `"Cuoi"` (không có newline) | `"Cuoi"` ở lần đầu, `null` lần sau | Dòng cuối hợp lệ rồi mới EOF |
| `"A\r\nB\r\n"` | `"A"`, `"B"`, rồi `null` | CRLF không được kèm vào chuỗi |
| `"\n\n"` | `""`, `""`, rồi `null` | Hai dòng rỗng, **không phải** một lần EOF |

Chú ý **`BufferedReader.readLine()` trả `null` khi EOF mà chưa đọc một ký tự nào của dòng mới**. Nếu đã đọc một số ký tự rồi gặp EOF mà chưa có newline, nó trả về dòng cuối trước; lần đọc sau mới trả `null`. Với `Console.readLine()`, hợp đồng chung cũng là trả `null` khi đạt EOF, nhưng việc nhập ký hiệu EOF trực tiếp trên terminal có thể phụ thuộc OS và console provider. Dùng file/pipe khi cần kiểm thử tái lập.

### Không trộn các trạng thái bằng một điều kiện

~~~java
String line = reader.readLine();

if (line == null) {
    // Kết thúc nguồn dữ liệu, không còn dòng tiếp theo.
} else if (line.isEmpty()) {
    // Có dòng nhưng không có ký tự nội dung.
} else if (line.isBlank()) {
    // Có ký tự, tất cả là khoảng trắng theo Unicode whitespace.
} else {
    // Có nội dung khác khoảng trắng.
}
~~~

Đây là **mã ghép vào method**. `String.isBlank()` có từ Java 11 và vẫn áp dụng cho Java 17+. Nếu dùng `line.strip()` rồi kiểm tra rỗng, đó là một **quy tắc chuẩn hóa theo nghiệp vụ**, không phải cách phân loại raw input nguyên bản. Một câu trả lời chỉ chứa khoảng trắng có thể là dữ liệu có ý nghĩa trong một ứng dụng khác; test phải theo hợp đồng đầu vào của sản phẩm.

**Không dùng** `line == ""` để kiểm tra giá trị chuỗi, vì toán tử `==` kiểm tra identity object, không phải nội dung. Không gọi `line.length()`, `line.isEmpty()` hoặc `line.strip()` trước khi xử lý trường hợp `null`.

## 3. EOF không phải lỗi I/O

`Console.readLine()` và `BufferedReader.readLine()` đều dùng **giá trị `null`** để biểu thị EOF theo hợp đồng. Điều này khác với `java.io.EOFException`: exception đó xuất hiện ở **một số API đọc dữ liệu khác** khi kết thúc luồng là bất ngờ, nhưng không phải kết quả mặc định của hai phương thức `readLine` đang xét.

Nếu ứng dụng đọc nhiều dòng cho tới hết input:

~~~java
String line;
while ((line = reader.readLine()) != null) {
    processLine(line);
}
~~~

Đây là đoạn minh họa, `processLine(...)` do ứng dụng cung cấp. Đoạn này sẽ vẫn **xử lý dòng rỗng**; nếu muốn bỏ dòng rỗng cần quy tắc riêng **bên trong vòng lặp**. Đừng viết `while (!(line = reader.readLine()).isBlank())` vì khi EOF, `line` là `null` và sẽ ném `NullPointerException`; hơn nữa nó sẽ coi dòng trắng là tín hiệu dừng dù chưa EOF.

Đối với terminal tương tác, Javadoc `Console` nêu rằng sau một sự kiện EOF (ví dụ tín hiệu được tạo từ bàn phím), **các lần đọc tiếp vẫn có thể thành công nếu người dùng sau đó nhập thêm ký tự trên console device**. Trong ứng dụng hỏi đáp thông thường, vẫn nên xem một kết quả `null` là điều kiện **kết thúc lần tương tác**. Không tự động hỏi lại vô hạn sau EOF, đặc biệt trong pipeline đã đóng input.

### EOF giữa chừng một biểu mẫu

Ví dụ chương trình hỏi tên rồi hỏi thành phố. Nếu bước đầu có dữ liệu nhưng bước thứ hai đạt EOF, quy tắc đúng thường là “form chưa hoàn tất”, không chuyển `null` thành `""` rồi ghi dữ liệu trống.

~~~java
String name = console.readLine("Tên: ");
if (name == null) {
    return;  // Không có thông tin tên.
}
String city = console.readLine("Thành phố: ");
if (city == null) {
    return;  // Input dừng trước khi đủ dữ liệu.
}
saveForm(name, city);
~~~

Đây là **đoạn minh họa trong method** với `console` hợp lệ và `saveForm(...)` của ứng dụng. Trong hệ thống thật, có thể phân biệt trạng thái `CANCELLED_BY_EOF` và `INVALID_EMPTY_LINE` để hiển thị thông báo và ghi audit chính xác.

## 4. “Gián đoạn” có ít nhất ba nghĩa

| Tình huống | Tín hiệu kỹ thuật | Có phải EOF? |
| --- | --- | --- |
| Reader gặp lỗi I/O | `IOException` từ `BufferedReader` / reader triển khai riêng | Không |
| Console gặp lỗi I/O | `IOError` từ `Console.readLine(...)` | Không |
| Một I/O implementation báo bị gián đoạn | Có thể là `InterruptedIOException`, `ClosedByInterruptException`, hoặc cơ chế riêng | Không |
| Thread được gọi `interrupt()` | Cờ interrupt và phản ứng **phụ thuộc thao tác đang chặn** | Không mặc nhiên |
| Lời gọi `Future.get(...)` bị interrupt | `InterruptedException` đối với thread đang **đợi Future** | Không; khác với thread đang đọc |
| Không có dữ liệu nhưng nguồn chưa đóng | `readLine()` có thể **block** | Không; chưa có kết quả |
| Luồng đã kết thúc, không còn ký tự | `readLine() == null` | Có |

`Console.readLine(...)` khai báo có thể ném **`IOError`**, không khai báo checked `InterruptedException`. `BufferedReader.readLine()` khai báo **`IOException`**. `InterruptedIOException` là subtype của `IOException`, mô tả một số tình huống truyền I/O bị ngắt; trường `bytesTransferred` có thể báo số byte đã truyền, nhưng **không biến exception thành “đã nhận một dòng hợp lệ”**.

**Rất quan trọng:** `SocketTimeoutException` là subtype của `InterruptedIOException`. Vì thế một nhánh `catch (InterruptedIOException ex)` có thể còn nhận lỗi timeout ở những loại input khác; nó **không chứng minh** ai đó đã gọi `Thread.interrupt()`. Nếu ứng dụng cần phân biệt timeout với interrupt thực, hãy kiểm tra loại exception cụ thể và hợp đồng của source.

### Vì sao `Thread.interrupt()` không phải “nút hủy readLine” chung?

Java `Thread.interrupt()` có xử lý xác định cho một số thao tác như `wait`/`sleep`/`join` và `InterruptibleChannel`. Nhưng **không có hợp đồng chung** bảo đảm việc interrupt một thread đang đọc qua `Console.readLine()` hay mọi `Reader/InputStream` sẽ khiến nó thoát ngay. Hành vi tùy backend, OS, channel, thread type và phiên bản JDK.

Đừng viết một test có dạng “bắt thread đọc console → gọi `thread.interrupt()` → đợi tối đa 100 ms → khẳng định thread luôn dừng”. Trên môi trường khác, nó có thể kẹt; test suite của CI cũng có thể bị treo.

- `Future.cancel(true)` **cố gắng interrupt** thread chạy task. Nó không thể bảo đảm code đọc console sẽ dừng và giải phóng resource.
- `Thread.interrupted()` **xóa cờ interrupt** của thread hiện tại khi đọc; trong code xử lý trạng thái, thường nên dùng `Thread.currentThread().isInterrupted()` nếu chỉ muốn kiểm tra mà không xóa.
- Khi bắt **`InterruptedException`** ở mức orchestration, thông thường cần khôi phục cờ với `Thread.currentThread().interrupt()` và thoát/lan truyền phù hợp. Không áp dụng cách khôi phục một cách máy móc chỉ vì bắt `InterruptedIOException`, bởi exception có thể đại diện cho timeout và không giống hợp đồng `InterruptedException`.

Với chương trình phải có **hard timeout** khi input do môi trường bên ngoài điều khiển, chạy input/console interaction trong **process riêng** rồi dùng một supervisor có thể kết thúc process an toàn hơn việc cố interrupt trực tiếp thread đọc trong JVM của server.

## 5. Chiến lược test: tách phân loại đầu vào khỏi thiết bị

Bạn không thể giả định unit test có console vật lý; `Console` được JVM cung cấp, `System.console()` có thể `null`, và test chạy trên IDE/CI hoặc chuyển hướng I/O thường không giống người gõ thật. Ngoài ra, các phiên bản JDK có thể có console provider khác nhau, khiến `console != null` không đủ để kết luận có terminal tương tác.

Hãy tách logic nghiệp vụ khỏi phần đọc:

~~~java
@FunctionalInterface
interface LineInput {
    String readLine() throws IOException;
}
~~~

Đây là **interface minh họa**, có thể là một nested interface trong class test, và cần import `IOException`. Tại runtime, implementation có thể gọi `Console.readLine("Lời nhắc: ")` hoặc `BufferedReader.readLine()`; tại unit test, implementation có thể đọc `StringReader` hoặc cố ý ném exception.

Ưu điểm:

1. **Không cần console thật** để kiểm tra EOF, rỗng, whitespace hoặc exception.
2. Mỗi case có input xác định, assert một kết quả rõ ràng.
3. Không thay `System.in` toàn cục làm ảnh hưởng những unit tests khác chạy song song.
4. Có thể kiểm tra nhiều lượt đọc trên **cùng reader**: ví dụ dòng cuối `"Cuoi"` không có newline, rồi EOF ở lượt sau.
5. Phân loại lỗi I/O riêng với EOF; không biến mọi exception thành `null` hoặc chuỗi rỗng.

Các phép thử này chứng minh **business logic khi nhận một kết quả từ input source**, không chứng minh mọi terminal thật đều phản ứng giống nhau trước phím Ctrl+C/Ctrl+D. Phần đó cần integration test có terminal hoặc PTY và policy timeout rõ ràng.

## 6. Chương trình Java 17+ hoàn chỉnh, kiểm thử tự động không cần terminal

Tạo **một tệp `ConsoleBoundaryTest.java`**. Chương trình có ba chế độ:

- Không argument: chạy **9 unit scenarios xác định**, gồm EOF/rỗng/dữ liệu cuối không có newline và các exception được **giả lập**.
- `--stdin`: đọc một dòng thực sự từ `System.in`, dùng để test bằng file/pipe mà không phụ thuộc console provider.
- `--console`: nếu có `System.console()` thì dùng `Console.readLine("...")`; nếu không có console thì báo không khả dụng. Chế độ này cần người dùng hoặc test runner có terminal/PTY phù hợp.

~~~java
import java.io.BufferedReader;
import java.io.Console;
import java.io.IOError;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.InterruptedIOException;
import java.io.StringReader;
import java.nio.charset.StandardCharsets;

public final class ConsoleBoundaryTest {
    private enum State { TEXT, EMPTY, WHITESPACE, EOF, INTERRUPTED_IO, IO_ERROR }
    private record Outcome(State state, String text) {}

    @FunctionalInterface
    private interface LineInput {
        String readLine() throws IOException;
    }

    private static Outcome classify(LineInput input) {
        try {
            String line = input.readLine();
            if (line == null) return new Outcome(State.EOF, null);
            if (line.isEmpty()) return new Outcome(State.EMPTY, line);
            if (line.isBlank()) return new Outcome(State.WHITESPACE, line);
            return new Outcome(State.TEXT, line);
        } catch (InterruptedIOException ex) {
            // This class can also represent a timeout; do not infer the cause.
            return new Outcome(State.INTERRUPTED_IO, null);
        } catch (IOException | IOError ex) {
            return new Outcome(State.IO_ERROR, null);
        }
    }

    private static String describe(Outcome result) {
        return result.state() == State.TEXT
                ? "TEXT(" + result.text() + ")"
                : result.state().name();
    }

    private static void test(String name, LineInput input) {
        System.out.println(name + " -> " + describe(classify(input)));
    }

    public static void main(String[] args) throws IOException {
        if (args.length > 0 && "--console".equals(args[0])) {
            Console console = System.console();
            if (console == null) {
                System.out.println("console -> UNAVAILABLE");
                return;
            }
            Outcome result = classify(
                    () -> console.readLine("Nhập một dòng: "));
            System.out.println("console -> " + describe(result));
            return;
        }

        if (args.length > 0 && "--stdin".equals(args[0])) {
            BufferedReader reader = new BufferedReader(
                    new InputStreamReader(System.in, StandardCharsets.UTF_8));
            System.out.print("Nhập một dòng: ");
            System.out.flush();
            Outcome result = classify(reader::readLine);
            System.out.println();
            System.out.println("stdin -> " + describe(result));
            return;
        }

        test("text", new BufferedReader(new StringReader("An\n"))::readLine);
        test("empty", new BufferedReader(new StringReader("\n"))::readLine);
        test("spaces", new BufferedReader(new StringReader("  \t\n"))::readLine);
        test("eof", new BufferedReader(new StringReader(""))::readLine);

        BufferedReader last = new BufferedReader(new StringReader("Cuoi"));
        test("last-no-newline", last::readLine);
        test("eof-after-last", last::readLine);

        test("simulated-interrupted-io", () -> {
            throw new InterruptedIOException("synthetic test");
        });
        test("simulated-io-error", () -> {
            throw new IOException("synthetic test");
        });
        test("simulated-console-ioerror", () -> {
            throw new IOError(new IOException("synthetic test"));
        });
    }
}
~~~

### 6.1. Biên dịch và chạy

Dùng JDK 17 hoặc mới hơn, tại thư mục chứa `ConsoleBoundaryTest.java`:

~~~bash
javac -encoding UTF-8 --release 17 ConsoleBoundaryTest.java
java ConsoleBoundaryTest
~~~

**Stdout chính xác** từ chế độ không argument (đã biên dịch và chạy trên JDK 24 với `--release 17`):

~~~text
text -> TEXT(An)
empty -> EMPTY
spaces -> WHITESPACE
eof -> EOF
last-no-newline -> TEXT(Cuoi)
eof-after-last -> EOF
simulated-interrupted-io -> INTERRUPTED_IO
simulated-io-error -> IO_ERROR
simulated-console-ioerror -> IO_ERROR
~~~

Phân tích kết quả:

1. `"An\n"` trở thành `TEXT(An)`, không mang `\n`.
2. `"\n"` trở thành `EMPTY`; `"  \t\n"` trở thành `WHITESPACE` vì `isBlank()` đúng.
3. `StringReader("")` lập tức đạt EOF, nên `readLine() == null`.
4. `StringReader("Cuoi")` không có newline vẫn trả `"Cuoi"` lần đầu. **Lần sau** mới là `EOF`. Đây là một regression test quan trọng, vì code đọc dòng thường xử lý sai trường hợp file cuối không có newline.
5. Ba case bắt đầu bằng `simulated-` **không mô phỏng phím Ctrl+C hoặc hủy thread thực**; chúng chỉ kiểm tra logic phân nhánh khi adapter ném `InterruptedIOException`, `IOException` và `IOError`. Unit test vì vậy ổn định và không bị treo.

**Chú ý việc phân loại:** trong chương trình, `INTERRUPTED_IO` là nhãn cho exception `InterruptedIOException`. Nhãn này không khẳng định thao tác là do `Thread.interrupt()` của Java hoặc chỉ do timeout gây ra. Nếu adapter có contract cụ thể về cancellation, nên mở rộng `Outcome` để lưu cause, error code hoặc loại timeout tương ứng. Không dùng demo này như một lớp phân tích mọi lỗi I/O có thể xảy ra.

### 6.2. Vì sao phải bắt `IOError` ngoài `IOException`?

`Console.readLine(...)` ném `IOError` khi gặp lỗi I/O; đây là subclass của `Error`, **không** là subclass của `IOException`. `BufferedReader.readLine()` có checked `IOException`. Adapter `LineInput` chỉ khai báo `throws IOException`, nhưng lambda gọi `Console.readLine(...)` vẫn hợp lệ vì `IOError` là unchecked.

Ví dụ bắt:

~~~java
try {
    String value = console.readLine("Nhập: ");
    // Kiểm tra value == null, isEmpty(), isBlank()...
} catch (IOError ex) {
    // Log/cảnh báo lỗi console I/O, quyết định kết thúc phiên nhập.
}
~~~

Đây là **mã minh họa** với `console` hợp lệ. Không bắt mọi `Error` rồi nuốt bỏ vì những lỗi JVM nghiêm trọng không thể mặc nhiên coi là input invalid. Demo cố ý bắt đúng `IOError` để có thể đánh giá trạng thái của thiết bị console.

### 6.3. Vì sao không in raw dữ liệu nhập trong mọi case?

Chương trình chỉ in nội dung raw với trạng thái `TEXT` để minh họa. Trong production, việc log trực tiếp dữ liệu người dùng có thể làm rò rỉ bí mật hoặc gây log/terminal injection (ký tự điều khiển ANSI, newline). `Outcome` trong hệ thống thật có thể giữ giá trị mà không log ra ngoài; test khẳng định trạng thái và nội dung trong bộ nhớ thay vì echo không cần thiết.

## 7. Kiểm thử bằng file và pipe (integration test stdin)

Những bài test sau **không** cần console thật vì chương trình được gọi với `--stdin`, buộc đi qua `BufferedReader(System.in)`. Điều này đặc biệt quan trọng vì `System.console()` có thể trả `null` trong CI/IDE và một số console provider có thể khác nhau khi I/O đã được redirect.

### 7.1. Linux/macOS/Bash

~~~bash
# Một dòng có dữ liệu:
printf 'An\n' | java ConsoleBoundaryTest --stdin

# Một dòng rỗng:
printf '\n' | java ConsoleBoundaryTest --stdin

# EOF ngay lập tức:
printf '' | java ConsoleBoundaryTest --stdin

# Dòng cuối không có newline:
printf 'Cuoi' | java ConsoleBoundaryTest --stdin
~~~

Các lệnh trên là **lệnh kiểm thử riêng biệt**. Không gộp cùng một process vì mỗi lần chạy chỉ đọc **một dòng**.

Stdout của test `printf 'An\n'`:

~~~text
Nhập một dòng: 
stdin -> TEXT(An)
~~~

Stdout của test chỉ có `printf '\n'`:

~~~text
Nhập một dòng: 
stdin -> EMPTY
~~~

Stdout của test `printf ''`:

~~~text
Nhập một dòng: 
stdin -> EOF
~~~

Stdout của test `printf 'Cuoi'`:

~~~text
Nhập một dòng: 
stdin -> TEXT(Cuoi)
~~~

Dấu cách cuối sau `Nhập một dòng: ` là một phần của prompt được in bởi chương trình; input từ pipe **không tự echo**, nên helper thêm newline sau khi đọc để in kết quả trên dòng mới. Với test kiểm tra byte-for-byte, chú ý line-ending của hệ điều hành (`\n` hoặc `\r\n`).

### 7.2. Windows PowerShell / cmd.exe

Trên Windows, có thể tạo input file **UTF-8 không BOM**:

~~~powershell
$utf8 = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText(
    "input.txt", "An" + [Environment]::NewLine, $utf8)
[System.IO.File]::WriteAllText(
    "empty.txt", [Environment]::NewLine, $utf8)
[System.IO.File]::WriteAllText("eof.txt", "", $utf8)
~~~

Rồi chạy file redirect bằng **cmd.exe**:

~~~bat
java ConsoleBoundaryTest --stdin < input.txt
java ConsoleBoundaryTest --stdin < empty.txt
java ConsoleBoundaryTest --stdin < eof.txt
~~~

`<` trong các lệnh trên là **cú pháp redirect của cmd.exe**; không nên giả định cùng cú pháp hoạt động trong Windows PowerShell 5.1. Nếu chạy trong PowerShell, có thể gọi một lệnh cmd có quote/escape phù hợp hoặc dùng công cụ cung cấp stdin qua process API. `eof.txt` là file không có byte, nên ở lần đọc đầu `BufferedReader.readLine()` trả `null`.

Đối với test tự động trên nhiều nền tảng, không dùng output mà một terminal **echo** dữ liệu nhập làm expected stdout. Hãy kiểm tra kết quả phân loại từ code và luồng stdout riêng; echo của terminal là một phần môi trường chứ không phải dữ liệu Java method trả về.

## 8. Kiểm thử terminal thật và Ctrl+C/Ctrl+D/Ctrl+Z

Chạy:

~~~bash
java ConsoleBoundaryTest --console
~~~

Khi có console tương tác, chương trình in prompt `Nhập một dòng: `. Có thể thử:

- Nhập `An` rồi Enter: trạng thái `TEXT(An)`.
- Nhấn Enter ngay: `EMPTY`.
- Nhập vài dấu cách rồi Enter: `WHITESPACE`.
- Trên terminal Unix, **Ctrl+D tại đầu dòng** thường biểu thị EOF.
- Trên Windows console, **Ctrl+Z rồi Enter** thường biểu thị EOF.

Đây là **hướng dẫn kiểm thử thủ công**, vì cách hệ điều hành/terminal/console provider phát sự kiện có thể khác nhau. Chú ý Ctrl+D sau khi đã gõ một phần nội dung có thể tạo **dòng cuối không newline** thay vì EOF ngay; kết quả phụ thuộc quy tắc terminal.

**Ctrl+C không phải unit test `InterruptedIOException`:** trên nhiều terminal nó gửi tín hiệu hủy đến process JVM, khiến process kết thúc thay vì `readLine()` ném một exception ổn định. Không viết test Java dựa vào việc “Ctrl+C phải tạo `InterruptedException`”, vì `Console.readLine` không có hợp đồng như vậy.

### Vì sao nên xác định chế độ terminal thay vì dựa vào `System.console()!=null`?

`System.console()` phụ thuộc cách JVM khởi động. Trong một số JDK 22–24 với JLine console provider, đối tượng console có thể tồn tại ngay cả khi I/O redirect; JDK 25 mặc định đổi provider. Với **Java 22+**, `Console.isTerminal()` giúp nhận biết console thực sự kết nối với terminal; API này **không có khi compile với `--release 17`**. Chương trình mẫu dùng option `--stdin` để kiểm thử nhất quán trên Java 17+ và không dựa vào heuristic provider.

Đối với GUI, IDE, background service và CI, nhiều khi không có một người thực sự điều khiển console. Tại những nơi này, hãy test logic với `StringReader` và test input thực qua file/pipe; chỉ yêu cầu PTY/console tương tác khi đó là phần hợp đồng sản phẩm.

## 9. Kiểm thử gián đoạn và timeout một cách an toàn

### 9.1. Unit test ngoại lệ: nhanh và xác định

Trong ví dụ hoàn chỉnh, các callback sau **cố ý** ném lỗi:

~~~java
test("simulated-interrupted-io", () -> {
    throw new InterruptedIOException("synthetic test");
});
test("simulated-io-error", () -> {
    throw new IOException("synthetic test");
});
test("simulated-console-ioerror", () -> {
    throw new IOError(new IOException("synthetic test"));
});
~~~

Đây là **mã ghép trong `ConsoleBoundaryTest`**. Nó chứng minh rằng `classify` không biến lỗi thành EOF/rỗng; nó không chứng minh hệ điều hành có thể interrupt lệnh console read theo cách tương tự. Nếu test yêu cầu một nguồn có thể hủy thật, hãy chọn abstraction/input provider **có contract cancellation**, không áp nó cho console.

### 9.2. `Future.cancel(true)` không phải hard timeout cho mọi console

Một đoạn kiểu sau chỉ **yêu cầu** hủy, không bảo đảm thread đọc console dừng:

~~~java
try {
    return future.get(2, TimeUnit.SECONDS);
} catch (TimeoutException timeout) {
    future.cancel(true); // Yêu cầu interrupt; không bảo đảm đọc Console sẽ thoát.
    throw timeout;
}
~~~

Đây là **mã minh họa trong method** đã có `future` (một `Future<T>`) và import `TimeUnit`, `TimeoutException`. Nếu `future.get` được thực thi trên một thread đang đợi và nhận `InterruptedException`, nên xử lý interruption **của thread đợi** riêng:

~~~java
try {
    return future.get();
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    throw interrupted;
}
~~~

Cũng là **đoạn minh họa trong method** có `future`, không phải file độc lập. Hai ví dụ cố ý tách biệt: bị timeout khi **đợi** task và task đọc console bị chặn là hai sự kiện khác nhau. Không tạo unit test mở thread chặn trên `System.in` rồi cứ đợi kết thúc sau `cancel(true)`; test có thể treo trên CI.

### 9.3. Hard timeout bằng process độc lập

Khi test một chương trình **có thể đợi input vô hạn**, chạy nó dưới một **process supervisor** và áp deadline bên ngoài JVM con. Trong Java 17, `Process.waitFor(timeout, unit)` trả `false` nếu process chưa kết thúc khi hết thời hạn. Sau đó có thể `destroy()`, và nếu cần `destroyForcibly()`.

~~~java
Process child = new ProcessBuilder(
        javaExecutable, "-cp", classPath,
        "ConsoleBoundaryTest", "--stdin").start();

try {
    if (!child.waitFor(2, TimeUnit.SECONDS)) {
        child.destroy();  // Đề nghị kết thúc một cách bình thường.
        if (!child.waitFor(1, TimeUnit.SECONDS)) {
            child.destroyForcibly();
            child.waitFor(); // Chờ process thực sự chấm dứt.
        }
    }
} finally {
    if (child.isAlive()) {
        child.destroyForcibly();
    }
}
~~~

Đây là **mã minh họa trong method**: `javaExecutable`, `classPath` được harness xác định; cần import `java.util.concurrent.TimeUnit` và xử lý `IOException`/`InterruptedException` theo hợp đồng. Khi harness giữ stdin của child **mở nhưng không ghi dữ liệu**, child sẽ chờ đọc; khi harness chủ động đóng stdin, child sẽ nhận EOF và có thể kết thúc bình thường.

Trong test production cần **drain hoặc redirect stdout/stderr** của child để tránh deadlock do buffer đầy; nên chờ process kết thúc sau khi yêu cầu destroy cưỡng bức và cleanup handle/resource. Hãy định nghĩa outcome riêng cho `TIMED_OUT` hoặc `CANCELLED` thay vì giả dạng `EOF`. Đây là hard timeout ở **ranh giới tiến trình**, không phải bảo đảm rằng `Thread.interrupt()` ngắt console read.

### 9.4. Không đồng nhất InterruptedIOException với kết quả từng phần

Nếu một lần đọc/ghi I/O ném `InterruptedIOException`, nó **không trả String** của dòng hoàn chỉnh. Dù `bytesTransferred` có giá trị, số đó không bảo đảm bạn có một chuỗi UTF-8 hoàn chỉnh hoặc một dòng hợp lệ, nhất là với ký tự multibyte. Ứng dụng nên xử lý lỗi/rollback hoặc thử lại theo hợp đồng của nguồn dữ liệu cụ thể, chứ không đoán phần còn thiếu rồi coi dữ liệu đó là hợp lệ.

## 10. Kiểm tra mật khẩu: EOF và rỗng cũng cần phân biệt

`Console.readPassword(...)` được dùng cho mật khẩu để tránh echo, trả **`char[]`**, không phải `String`. Nó cũng trả `null` khi EOF. Với một dòng không có ký tự, kết quả có thể là **mảng dài 0**; đây là một dữ liệu nhập rỗng, **không phải EOF**.

~~~java
Console console = System.console();
if (console == null) {
    throw new IllegalStateException("Cần console phù hợp để nhập mật khẩu.");
}

char[] password = console.readPassword("Mật khẩu: ");
if (password == null) {
    System.out.println("EOF khi nhập mật khẩu.");
    return;
}

try {
    if (password.length == 0) {
        System.out.println("Mật khẩu không được rỗng.");
    } else {
        // Chuyển cho thành phần xác thực mà không in lại dữ liệu.
    }
} finally {
    java.util.Arrays.fill(password, '\0');
}
~~~

Đây là **đoạn minh họa trong method**. Không sử dụng `readLine` thay cho `readPassword` để thử test mật khẩu, vì có thể để lộ ký tự qua terminal echo. Không lưu mật khẩu vào log/snapshot/test output; sau khi xử lý nên xóa `char[]` khi còn quyền sở hữu.

## 11. Bảng các lỗi thường gặp

| Sai lầm | Điều xảy ra | Cách sửa |
| --- | --- | --- |
| Dùng `readLine() == ""` | `==` so sánh reference chứ không phải nội dung | Sau kiểm tra `null`, dùng `isEmpty()`/`isBlank()` |
| Đọc `null` rồi gọi `strip()` | `NullPointerException` | Xử lý EOF trước |
| Xem dòng chỉ có tab/space là rỗng hoàn toàn | Mất phân biệt dữ liệu raw | `isEmpty` khác `isBlank`; chuẩn hóa theo chính sách |
| Cho rằng file không có newline ở cuối là không hợp lệ | Làm mất dòng cuối | Kiểm thử input `"Cuoi"` rồi EOF ở lượt sau |
| Bắt `EOFException` cho `Console.readLine` | Không phản ánh giá trị trả về thông thường | Kiểm tra kết quả `null` |
| Dùng `System.console().readLine` trong CI | Có thể `NullPointerException` khi không có console | Kiểm tra null; có reader/CLI mode thay thế |
| Nhầm `IOError` thành `IOException` | Miss nhánh lỗi console | Xử lý loại exception đúng ở boundary |
| Bắt `IOException` rồi trả `""` | Biến lỗi I/O thành dữ liệu nhập rỗng | Trạng thái `IO_ERROR` riêng |
| Bắt `InterruptedIOException` rồi kết luận `Thread.interrupt` đã xảy ra | Có thể là timeout hoặc nguyên nhân riêng của I/O provider | Phân tích cause/subtype theo contract |
| Cho rằng `Future.cancel(true)` chắc chắn dừng đọc console | Test treo/worker không dừng | Input source có cancellation contract hoặc process supervisor |
| Không giới hạn thời gian integration test | Một lời nhắc chờ vĩnh viễn trên CI | Cấp input cụ thể hoặc test dưới hard timeout tiến trình |
| Dùng một test cho cả terminal echo và piped stdin | Output dễ khác nhau theo OS/provider | Unit test phân loại; integration test chế độ riêng |
| Trộn `Scanner`, `BufferedReader` và `System.in.read` cùng nguồn | Input có thể bị buffer/read-ahead | Dùng một abstraction và một reader nhất quán |
| Không làm rõ encoding khi redirect input | Chuỗi Unicode bị lỗi trên vài hệ điều hành | Dùng cùng charset ở file, pipe và `InputStreamReader` |
| Dùng `Console.readLine` cho mật khẩu | Thông tin nhạy cảm có thể bị echo | Dùng `readPassword` và xóa mảng sau xử lý |

## 12. Checklist QA cho tính năng đọc dòng

Trước khi phát hành một CLI hoặc một tác vụ đọc stdin:

1. **Hợp đồng trạng thái rõ ràng:** `TEXT`, `EMPTY`, `WHITESPACE`, `EOF`, `IO_ERROR` và `INTERRUPTED_IO`/`TIMEOUT` nếu môi trường hỗ trợ.
2. **Kiểm tra giá trị raw:** giữ chính xác dòng đã đọc; chỉ `strip`/normalize khi nghiệp vụ yêu cầu.
3. **Kiểm thử không cần terminal:** dùng `StringReader` hoặc một `LineInput` giả cho unit tests, không phụ thuộc `System.console()`.
4. **Kiểm thử lần đọc liên tiếp:** trường hợp có dòng cuối không có newline, rồi mới EOF.
5. **Kiểm thử exception được chèn vào:** `IOException` và `IOError` không bị xem là EOF; `InterruptedIOException` được phân loại riêng.
6. **Kiểm thử thực với stdin:** file có dữ liệu, newline đơn, file rỗng, cuối không có newline, CRLF nếu chạy Windows.
7. **Kiểm thử terminal thật khi cần:** prompt, echo, EOF key sequence, môi trường không có console và các provider/JDK được hỗ trợ.
8. **Giới hạn thời gian test:** không giả định interrupt một lời gọi đọc terminal có tác dụng tức thời; dùng process timeout nếu có nguy cơ block.
9. **Quản lý resource:** không tùy tiện đóng `System.in` dùng chung hoặc trộn buffered readers; cleanup process con nếu timeout.
10. **An toàn đầu vào:** không echo mật khẩu, giới hạn độ dài và tần suất nhập khi cần, không log input có control characters/secret.

## 13. Câu hỏi tự kiểm tra

1. **`BufferedReader.readLine()` trên `StringReader("")` trả gì?** `null` vì EOF trước ký tự đầu tiên.
2. **`StringReader("\n")` trả gì ở lần đọc đầu?** `""`; lần tiếp là `null`.
3. **`StringReader("Last")` không có newline có làm mất dòng cuối không?** Không. Lần đầu trả `"Last"`, lần kế trả `null`.
4. **`" \t ".isEmpty()` và `.isBlank()` khác nhau thế nào?** `isEmpty()` là `false`, `isBlank()` là `true`.
5. **`Console.readLine(...)` có luôn ném `EOFException` khi EOF không?** Không; nó trả `null` theo hợp đồng.
6. **Lỗi console I/O thường được báo qua `IOException` hay `IOError`?** `IOError` từ `Console.readLine`.
7. **Vì sao test phải giả lập `InterruptedIOException` thay vì ép interrupt console trên CI?** Để xác minh xử lý trạng thái ổn định, không phụ thuộc cách backend có/không hỗ trợ interruption.
8. **`Future.cancel(true)` đủ để đặt hard timeout cho input từ terminal không?** Không; đó là yêu cầu interrupt, không phải kill bắt buộc.
9. **`System.console() == null` có đồng nghĩa EOF không?** Không. Nó chỉ nghĩa JVM không cung cấp console theo cách khởi chạy/provider; `System.in` có thể vẫn còn dữ liệu.
10. **Dữ liệu chỉ có khoảng trắng khác dòng rỗng ra sao?** `isEmpty` false nhưng `isBlank` true; quy tắc chấp nhận phụ thuộc nghiệp vụ.
11. **EOF ở lượt nhập mật khẩu khác password rỗng không?** Có: `null` so với `char[]` có độ dài 0.
12. **Muốn test chương trình đang chờ input mãi phải làm gì?** Cấp input/EOF bằng pipe hoặc chạy dưới process supervisor có timeout và cleanup.

## 14. Tham khảo chính thức đang còn hiệu lực

- [Java SE 25 — `Console`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/Console.html): `readLine`, EOF, `IOError`, `readPassword`, console provider.
- [Java SE 25 — `BufferedReader`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/BufferedReader.html): dòng kết thúc ở LF/CR/CRLF/EOF, kết quả `null`, `IOException`.
- [Java SE 25 — `StringReader`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/StringReader.html): tạo nguồn ký tự trong bộ nhớ cho unit tests.
- [Java SE 25 — `InterruptedIOException`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/InterruptedIOException.html): loại exception và `bytesTransferred`.
- [Java SE 25 — `Thread.interrupt`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.html#interrupt()): bảo đảm/hạn chế hủy các loại thao tác blocking.
- [Java SE 25 — `Process.waitFor(timeout, unit)`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Process.html#waitFor(long,java.util.concurrent.TimeUnit)): deadline khi chạy process con.
- [Java SE 25 — `Future.cancel(boolean)`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Future.html#cancel(boolean)): yêu cầu hủy task và giới hạn bảo đảm của interruption.
- [Java SE 25 — `System.console`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/System.html#console()): môi trường không có console.

**Tổng kết:** EOF là một **giá trị `null` của phép đọc dòng**, rỗng là **`""`**, chỉ khoảng trắng là **dòng không rỗng nhưng `isBlank() == true`**, I/O failure là **ngoại lệ**, còn thao tác đang block chưa có kết quả. Kiểm thử tốt cần **nguồn input được điều khiển**, **bảng trạng thái tường minh**, và **quy tắc timeout phù hợp môi trường**, không dựa vào một phép interrupt chung cho mọi loại console.