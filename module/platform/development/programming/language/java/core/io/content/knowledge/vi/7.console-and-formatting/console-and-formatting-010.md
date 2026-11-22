# Không vô tình đóng các stream chuẩn dùng chung trong Java

Trong ứng dụng Java, `System.in`, `System.out` và `System.err` thường được sử dụng ở nhiều nơi: nhập lệnh trong console, in kết quả, ghi thông báo và báo lỗi. Một thao tác tưởng hợp lý như đặt `Scanner(System.in)` vào `try-with-resources` trong một hàm tiện ích có thể khiến **luồng nhập chuẩn bị đóng** khi hàm kết thúc. Những phần còn lại của chương trình khi đó không thể tiếp tục đọc input như trước.

Nguyên tắc chính của bài học: **chỉ đóng tài nguyên mà mình sở hữu hoặc được giao quyền đóng**. Một helper chỉ mượn stream chuẩn để đọc hay ghi **không nên kết thúc vòng đời stream đó**. Khi thêm `Scanner`, `BufferedReader`, `PrintWriter` hoặc các wrapper khác, cần nhớ rằng gọi `close()` trên wrapper có thể đóng **luôn stream nền**.

## 1. Ba stream chuẩn của Java là gì?

Lớp `java.lang.System` cung cấp ba trường tĩnh dùng chung trong tiến trình Java:

| Stream | Kiểu | Vai trò thông thường | Ví dụ |
|---|---|---|---|
| `System.in` | `InputStream` | Nhận dữ liệu đầu vào chuẩn (stdin) | Đọc nội dung người dùng nhập hoặc dữ liệu được chuyển hướng từ tệp |
| `System.out` | `PrintStream` | Xuất kết quả/thông tin thông thường (stdout) | `System.out.println("OK")` |
| `System.err` | `PrintStream` | Xuất thông báo lỗi/chẩn đoán (stderr) | `System.err.println("Lỗi nhập liệu")` |

`System.in` cung cấp **byte**, còn `System.out` và `System.err` là các đối tượng `PrintStream` có phương thức `print`/`println`/`printf` thuận tiện. Những tên gọi này mô tả **kênh I/O**, không bảo đảm rằng đầu kia luôn là một bàn phím hoặc màn hình vật lý.

Ví dụ chạy từ shell:

~~~bash
java Main < input.txt > output.txt 2> error.txt
~~~

Lệnh có ý nghĩa: stdin của Java được nối với `input.txt`, stdout được chuyển tới `output.txt` và stderr tới `error.txt`. Trong IDE, môi trường test, container hoặc dịch vụ, những stream này cũng có thể được nối với hệ thống khác. Bởi vậy, một phương thức sâu bên trong ứng dụng **không được tự xem mình là chủ sở hữu độc quyền** của chúng.

Các trường `System.in`, `System.out`, `System.err` có thể được thay thế bằng `System.setIn(...)`, `System.setOut(...)` và `System.setErr(...)` trong phạm vi ứng dụng có quyền phù hợp, chẳng hạn trong test hoặc khi nhúng ứng dụng. Điều này càng củng cố yêu cầu phân định **ai cung cấp stream, ai dùng và ai đóng**.

## 2. Vì sao đóng stream chuẩn trong helper lại nguy hiểm?

Giả sử chương trình có hai giai đoạn:

~~~text
main()
  ├── readProfile(): đọc một dòng từ System.in
  └── readCommand(): đọc một lệnh khác từ System.in
~~~

Nếu `readProfile()` tạo `Scanner` bọc `System.in` rồi đóng scanner khi trả về, nó có thể **đóng luôn `System.in`**. Khi `readCommand()` cố gắng đọc tiếp, nó có thể nhận lỗi hoặc không còn dữ liệu đọc được.

Một mẫu code dễ mắc lỗi:

~~~java
// KHÔNG NÊN nếu sau hàm này ứng dụng vẫn cần System.in.
static String readOneName() {
    try (Scanner scanner = new Scanner(System.in)) {
        return scanner.nextLine();
    } // scanner.close() cũng đóng nguồn đọc System.in.
}
~~~

Đây là **đoạn minh họa lỗi ownership**, không phải ví dụ được khuyến khích. `Scanner.close()` gọi `close()` trên input source của nó nếu source triển khai `Closeable`; `System.in` là `InputStream` và triển khai giao diện này.

Vấn đề không phải bản thân `try-with-resources`: cơ chế đó **đúng** khi tài nguyên nằm trong phạm vi sở hữu của hàm. Sai lầm là đặt một **wrapper đang mượn tài nguyên chung** vào khu vực tự động đóng.

Một lỗi tương tự ở stdout:

~~~java
// KHÔNG NÊN: đóng wrapper có thể đóng System.out.
static void printReport() {
    try (PrintWriter writer = new PrintWriter(System.out)) {
        writer.println("Báo cáo hoàn tất");
    }
}
~~~

`PrintWriter.close()` đóng writer và tầng output bên dưới. Vì `System.out` là luồng chung, những nơi in log hoặc kết quả sau đó có thể không còn hoạt động như mong đợi. `PrintStream` như `System.out` thường ghi nhận lỗi thay vì ném `IOException` từ các phương thức `print`/`println`, khiến việc vô tình đóng stdout có thể không biểu hiện bằng một ngoại lệ rõ ràng.

**Đóng wrapper** thường khác với **ngừng dùng wrapper**. Khi caller sở hữu luồng chuẩn, một helper có thể dùng wrapper tạm để đọc/ghi nhưng không được tự ý gọi `close()` trên nó.

## 3. Quyền sở hữu và vòng đời: cần hỏi ai có trách nhiệm đóng?

**Ownership (quyền sở hữu)** là thỏa thuận về việc bên nào chịu trách nhiệm kết thúc tài nguyên. Nó không được suy ra chỉ từ kiểu tham số `InputStream` hoặc `OutputStream`.

### Trường hợp A — Hàm tự mở tài nguyên: hàm chịu trách nhiệm đóng

Ví dụ code mở tệp để đọc:

~~~java
static String readFile(Path path) throws IOException {
    try (BufferedReader reader =
                 Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
        return reader.readLine();
    }
}
~~~

Đây là **phương thức minh họa**, cần import `java.io.*`, `java.nio.file.*` và `java.nio.charset.StandardCharsets`. Stream tệp được tạo bên trong hàm; sau khi đọc xong, hàm không cần nó nữa. Dùng `try-with-resources` để đóng là hợp lý.

### Trường hợp B — Hàm nhận stream do caller cung cấp: hàm chỉ mượn

~~~java
static void writeGreeting(PrintStream destination, String name) {
    destination.println("Xin chào, " + name);
    // Không destination.close(): caller đang sở hữu.
}
~~~

Đây là **phương thức minh họa** nhận `PrintStream` từ caller. Nó có thể dùng với `System.out`, `System.err` hoặc một `PrintStream` khác do caller tạo. Hợp đồng của hàm là **ghi một dòng**, không phải **kết thúc nơi nhận**.

### Trường hợp C — Luồng chuẩn được môi trường quản lý: đừng đóng ở code cục bộ

`System.in`, `System.out`, `System.err` thường tồn tại trong suốt vòng đời ứng dụng và có thể được chia sẻ bởi thư viện, framework, command loop, REPL hoặc thành phần ghi log. Một hàm đọc một câu hỏi hoặc in một báo cáo chỉ là **người dùng tạm thời**.

| Ai tạo/cấp tài nguyên? | Bên sử dụng | Bên thường đóng |
|---|---|---|
| Hàm mở `FileInputStream`/`Files.newInputStream` | Chính hàm đó | Hàm, thường với `try-with-resources` |
| Caller truyền `InputStream` vào thư viện | Thư viện/helper chỉ mượn | Caller, trừ khi hợp đồng nói rõ chuyển quyền sở hữu |
| Java runtime hoặc môi trường ứng dụng cấp `System.in/out/err` | Nhiều phần của ứng dụng | Tầng quản lý vòng đời ứng dụng/môi trường; helper không tự đóng |
| Hàm tự tạo `ByteArrayInputStream` hoặc `ByteArrayOutputStream` | Hàm | Hàm; đóng nhiều stream bộ nhớ có thể không giải phóng tài nguyên hệ điều hành nhưng vẫn cần hợp đồng rõ |
| Framework cung cấp stream phản hồi/request | Code callback | Theo hợp đồng framework |

**Ghi nhớ:** quyền sở hữu là **hợp đồng API**. Khi xây dựng phương thức công khai, hãy viết rõ “phương thức không đóng luồng đầu vào/đầu ra được truyền vào” hoặc “phương thức nhận quyền sở hữu và sẽ đóng luồng”.

## 4. Các wrapper có thể đóng stream chuẩn như thế nào?

Một stream gốc có thể được bọc nhiều tầng. Khi đóng tầng ngoài, nhiều lớp tiêu chuẩn chuyển tiếp thao tác đóng xuống tầng trong:

~~~text
Scanner.close() ------------------------> System.in.close()

BufferedReader.close()
  -> InputStreamReader.close() ----------> System.in.close()

PrintWriter.close()
  -> OutputStreamWriter.close() ---------> System.out.close()

BufferedOutputStream.close() -----------> System.out.close()
~~~

Sơ đồ mô tả các trường hợp khi wrapper thực sự bọc **chính các stream chuẩn**. Việc đóng sâu hay không phải xem hợp đồng của wrapper cụ thể; những ví dụ này minh họa hành vi các wrapper JDK thông thường.

### `Scanner`

`Scanner` có thể nhận `InputStream`, `Readable`, `File`, `Path` hoặc `String` tùy constructor. Nếu source là `Closeable`, `scanner.close()` cũng đóng source. Vì thế:

~~~java
Scanner scanner = new Scanner(System.in, StandardCharsets.UTF_8);
String name = scanner.nextLine();
// Không scanner.close() nếu ứng dụng còn dùng System.in.
~~~

Đây là **đoạn minh họa**, cần import `java.util.Scanner` và `java.nio.charset.StandardCharsets`. Nếu helper thực sự tự sở hữu source, cách đóng có thể khác.

### `BufferedReader` và `InputStreamReader`

~~~java
BufferedReader reader = new BufferedReader(
        new InputStreamReader(System.in, StandardCharsets.UTF_8));
String line = reader.readLine();
// Không reader.close() trong một helper chỉ mượn System.in.
~~~

`BufferedReader` bọc `InputStreamReader`; đóng reader ngoài cùng sẽ đóng adapter ký tự, từ đó đóng stream byte bên dưới. Bổ sung điều quan trọng: **reader có bộ đệm có thể đọc trước nhiều byte/ký tự**. Nếu tạo nhiều `Scanner`/`BufferedReader` riêng cùng đọc `System.in`, chúng có thể tranh chấp dữ liệu ngay cả khi không đóng stream. Hãy dùng **một đối tượng đọc được chia sẻ ở tầng phù hợp** cho cùng phiên nhập.

### `PrintWriter`, `OutputStreamWriter` và `PrintStream`

~~~java
Writer writer = new OutputStreamWriter(System.out, StandardCharsets.UTF_8);
writer.write("Xin chào\n");
writer.flush(); // Đẩy buffer ký tự xuống output được mượn.
// Không writer.close() trong helper chỉ mượn System.out.
~~~

`OutputStreamWriter` chuyển ký tự thành byte theo charset đã chỉ định. `flush()` đẩy dữ liệu trong buffer của writer xuống output bên dưới; khác với `close()`, nó không kết thúc luồng. Nếu `PrintWriter` bao `System.out`, `PrintWriter.close()` cũng đóng nơi nhận bên dưới theo hợp đồng wrapper.

**Lưu ý về charset:** `System.out` vốn là `PrintStream` có cơ chế chuyển ký tự thành byte cho đích cấu hình của runtime. Tạo thêm `OutputStreamWriter(System.out, UTF_8)` tạo một tầng mã hóa riêng; chỉ nên làm khi **chủ đích** muốn byte UTF-8 đi qua tầng đó và nó tương thích môi trường. Với việc in console thông thường, gọi trực tiếp `System.out.print/println/printf` thường rõ ràng hơn.

## 5. Ví dụ Java 17: một helper chỉ mượn stream, owner đóng sau

Để kiểm tra hành vi **không đóng nguồn/đích do caller quản lý** mà không gây ảnh hưởng đến `System.in`/`System.out` thật, chương trình dùng hai stream thử nghiệm có cờ đánh dấu mỗi lần `close()` được gọi.

Helper `greet` nhận input và output. Nó tạo `Scanner` để đọc một dòng, `OutputStreamWriter` để ghi UTF-8, gọi `flush()` khi cần và **không gọi `close()`**. Sau khi helper trả về, caller có thể ghi tiếp vào output. Chỉ **owner** mới đặt hai nguồn/đích vào `try-with-resources`.

Lưu toàn bộ mã vào **`SharedStandardStreamsDemo.java`**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.FilterInputStream;
import java.io.FilterOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.io.OutputStreamWriter;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.util.Scanner;

public class SharedStandardStreamsDemo {
    static final class TrackedInput extends FilterInputStream {
        boolean closed;

        TrackedInput(InputStream delegate) {
            super(delegate);
        }

        @Override
        public void close() throws IOException {
            closed = true;
            super.close();
        }
    }

    static final class TrackedOutput extends FilterOutputStream {
        boolean closed;

        TrackedOutput(OutputStream delegate) {
            super(delegate);
        }

        @Override
        public void close() throws IOException {
            closed = true;
            super.close();
        }
    }

    // Chỉ mượn input/output; quyền close thuộc về caller.
    static void greet(InputStream input, OutputStream output)
            throws IOException {
        Scanner scanner = new Scanner(input, StandardCharsets.UTF_8);
        Writer writer = new OutputStreamWriter(output, StandardCharsets.UTF_8);

        writer.write("Tên: ");
        writer.flush();
        if (scanner.hasNextLine()) {
            String name = scanner.nextLine();
            writer.write("Xin chào, " + name + "\n");
            writer.flush();
        }
        // Không scanner.close() hay writer.close().
    }

    public static void main(String[] args) throws IOException {
        ByteArrayOutputStream capture = new ByteArrayOutputStream();
        TrackedInput input = new TrackedInput(
                new ByteArrayInputStream(
                        "Mai\n".getBytes(StandardCharsets.UTF_8)));
        TrackedOutput output = new TrackedOutput(capture);

        try (input; output) {
            greet(input, output);
            output.write("Tiếp tục\n".getBytes(StandardCharsets.UTF_8));
            output.flush();

            System.out.println("Trong try: inputClosed=" + input.closed
                    + ", outputClosed=" + output.closed);
        }

        System.out.println("Sau try: inputClosed=" + input.closed
                + ", outputClosed=" + output.closed);
        System.out.println("Nội dung đã ghi:");
        System.out.print(capture.toString(StandardCharsets.UTF_8));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 SharedStandardStreamsDemo.java
java SharedStandardStreamsDemo
~~~

Kết quả khi console hiển thị được tiếng Việt:

~~~text
Trong try: inputClosed=false, outputClosed=false
Sau try: inputClosed=true, outputClosed=true
Nội dung đã ghi:
Tên: Xin chào, Mai
Tiếp tục
~~~

**Giải thích:**

1. `TrackedInput` và `TrackedOutput` là wrapper đánh dấu lời gọi `close()`, bọc byte stream trong bộ nhớ. Chúng chỉ nhằm kiểm chứng **vòng đời được điều khiển bởi caller**.
2. `greet` dùng dữ liệu nhập `"Mai\n"`, tạo output từ `Writer`, gọi `flush()` để hoàn tất phần ghi tại thời điểm đó nhưng **không đóng wrapper**.
3. Ngay khi `greet` trả về, hai biến `closed` vẫn `false`. Caller còn dùng `output.write(...)` thành công để ghi thêm `"Tiếp tục\n"`.
4. Thoát khối `try (input; output)`, Java tự gọi `close()` cho các tài nguyên mà **caller đã khai báo sở hữu** (theo thứ tự ngược lúc khai báo: output rồi input). Sau đó cả hai cờ trở thành `true`.
5. `System.out` thật chỉ được sử dụng để báo kết quả; ví dụ **không đóng hoặc thay thế** bất kỳ stream chuẩn nào của tiến trình.
6. `ByteArrayOutputStream` có thể cung cấp nội dung đã ghi ngay cả sau khi bị đóng; đây là đặc tính của lớp này. Không suy diễn rằng file/socket cũng giữ hành vi tương tự sau `close()`.

Trong một ứng dụng thật, nếu `greet(System.in, System.out)` được gọi từ command loop, hợp đồng mượn stream vẫn có ý nghĩa: helper không được đóng luồng chuẩn vì caller có thể nhập/xuất tiếp. Tuy nhiên, không nên liên tục tạo `Scanner` mới trên `System.in` trong command loop vì scanner có thể **đọc trước** và giữ lại dữ liệu trong buffer riêng. Thay vào đó, caller có thể tạo **một reader/scanner dùng chung**, rồi truyền nó vào các helper.

## 6. Cách thiết kế API tốt hơn: caller sở hữu scanner, helper chỉ sử dụng

Nếu cả chương trình phải hỏi nhiều câu, đưa việc khởi tạo và quản lý bộ đọc ra tầng ứng dụng:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Scanner;

public class SharedConsoleReader {
    static void askName(Scanner scanner) {
        System.out.print("Tên: ");
        if (scanner.hasNextLine()) {
            String name = scanner.nextLine();
            System.out.println("Xin chào, " + name);
        }
        // Helper không đóng scanner.
    }

    static void askCity(Scanner scanner) {
        System.out.print("Thành phố: ");
        if (scanner.hasNextLine()) {
            String city = scanner.nextLine();
            System.out.println("Bạn ở " + city);
        }
        // Vẫn không đóng scanner.
    }

    public static void main(String[] args) {
        Scanner sharedScanner =
                new Scanner(System.in, StandardCharsets.UTF_8);
        askName(sharedScanner);
        askCity(sharedScanner);
        // Không đóng System.in trong chương trình minh họa.
    }
}
~~~

Đây là **chương trình Java 17 độc lập**, lưu thành `SharedConsoleReader.java`. Khi chạy `java SharedConsoleReader`, người dùng sẽ lần lượt nhập tên và thành phố. Output tương tác phụ thuộc câu trả lời; ví dụ nhập `Lan` rồi `Đà Nẵng`:

~~~text
Tên: Lan
Xin chào, Lan
Thành phố: Đà Nẵng
Bạn ở Đà Nẵng
~~~

Trong thực tế, nhiều terminal sẽ hiển thị lại chữ người dùng gõ trên cùng dòng prompt. Phần ví dụ trên là **một phiên tương tác mẫu**, không phải chuỗi output cố định cho mọi trường hợp.

Lợi ích của cách thiết kế này:

- Chỉ có **một** `Scanner` đọc `System.in`, giảm nguy cơ nhiều buffer tranh chấp.
- Mỗi helper nhận sẵn reader và không quyết định vòng đời toàn ứng dụng.
- Việc test dễ hơn: caller có thể truyền `Scanner` được tạo từ `String`, còn đầu ra có thể được thiết kế bằng tham số `PrintStream` thay vì ghi trực tiếp `System.out`.
- Lớp điều phối quyết định khi nào luồng nhập thật sự kết thúc, dựa trên hợp đồng ứng dụng.

Không có yêu cầu phải đóng `System.in` cuối `main` ở mọi ứng dụng console. Khi tiến trình kết thúc, hệ điều hành thu hồi các resource của tiến trình; việc tránh đóng stream chuẩn trong helper là để không gây tác dụng phụ cho các thành phần vẫn còn chạy. Với tài nguyên **do ứng dụng tự mở**, vẫn phải đóng đúng lúc.

## 7. `flush()` không phải `close()`

Khi ghi qua tầng có buffer, dữ liệu có thể chưa tới đích ngay sau `write()`. Ba thao tác khác nhau:

| Thao tác | Mục đích | Ảnh hưởng tới quyền sử dụng tiếp |
|---|---|---|
| `write(...)` / `print(...)` | Gửi ký tự/byte vào API xuất, có thể qua buffer | Thường có thể ghi tiếp |
| `flush()` | Yêu cầu đưa nội dung đã đệm xuống tầng output bên dưới | **Không đóng**, vẫn có thể ghi tiếp |
| `close()` | Kết thúc vòng đời stream/wrapper, thường thực hiện flush theo hợp đồng rồi đóng tầng dưới | **Không nên sử dụng tiếp** |

Trong helper dùng `Writer` bọc `System.out`, nếu cần đảm bảo phần output đệm được đẩy xuống trước khi trả về thì có thể gọi `writer.flush()`; đó **không phải lý do để gọi `writer.close()`**.

`PrintWriter` có những constructor có tùy chọn **autoFlush**, nhưng không nên cho rằng “autoFlush = true” khiến mọi phương thức ghi đều flush. Với `PrintWriter`, auto-flush gắn với các thao tác như `println`, `printf` và `format` theo hợp đồng của lớp; `write` hay `print` đơn thuần có thể không kích hoạt như mong muốn. Khi cần ranh giới output rõ ràng, kiểm tra hợp đồng và gọi `flush()` phù hợp.

Tương tự, `System.out.flush()` và `System.err.flush()` thường an toàn hơn `close()` khi bạn chỉ muốn đẩy phần đã ghi. Nhưng `flush()` không bảo đảm dữ liệu đã được lưu bền vững trên đĩa hoặc đầu nhận mạng đã xử lý xong.

## 8. Những điều dễ bị bỏ sót

### Đóng `System.out` đôi khi không báo lỗi ngay

Các thao tác `print`/`println` của `PrintStream` không truyền `IOException` trực tiếp như nhiều API output khác. Vì vậy, sau khi một thư viện vô tình đóng stdout, các lệnh in sau đó **có thể không hiển thị** thay vì lập tức ném một ngoại lệ dễ thấy. `PrintStream.checkError()` cho phép kiểm tra trạng thái lỗi theo hợp đồng, nhưng **kiểm tra lỗi không thay thế** việc thiết kế ownership đúng.

Không nên tạo chương trình thử trên `System.out` thật bằng cách cố ý gọi `System.out.close()` để “xem có sao không”, nhất là trong IDE, test runner, notebook hoặc tiến trình có nhiều chức năng dùng chung.

### `System.err` cũng là tài nguyên chung

Không được cho rằng stderr có thể đóng tùy ý vì “chỉ ghi lỗi”. Công cụ logging, trình xử lý ngoại lệ và framework vẫn có thể cần `System.err` sau lời gọi của bạn. Việc terminal ghép stdout và stderr thành cùng một nơi hiển thị **không làm thay đổi** vòng đời sở hữu của hai đối tượng `PrintStream`.

### Close wrapper khi caller vẫn cần stream là lỗi hợp đồng

Ví dụ:

~~~java
// SAI nếu caller cần dùng System.out tiếp:
try (BufferedOutputStream buffered = new BufferedOutputStream(System.out)) {
    buffered.write("Hello\n".getBytes(StandardCharsets.UTF_8));
} // BufferedOutputStream.close() đóng stream nền.
~~~

Đây là **đoạn minh họa hành vi không nên dùng**. Import cần thiết gồm `java.io.BufferedOutputStream` và `java.nio.charset.StandardCharsets`; phương thức chứa mã phải xử lý/khai báo `IOException`. Nếu thật sự cần buffer, hãy quản lý tầng này ở cấp sở hữu stream hoặc xây API nhận một writer được caller quản lý, và flush theo ranh giới hợp đồng.

### Redirect stream trong test cũng cần khôi phục

Khi test cần chặn output, có thể thay `System.out` bằng `PrintStream` ghi vào `ByteArrayOutputStream`. Việc gọi `System.setOut(...)` thay đổi **trạng thái toàn cục** và có thể ảnh hưởng test khác chạy cùng lúc. Nếu bắt buộc thay, cần khôi phục stream gốc bằng `finally` và chỉ đóng stream tạm mà test đã tạo; tránh vô tình đóng stream gốc. Đối với code thư viện, một thiết kế nhận `PrintStream`/`Writer` qua tham số thường dễ test hơn và ít ảnh hưởng toàn cục.

### `try-with-resources` không sai; đặt sai quyền sở hữu mới gây lỗi

~~~java
// ĐÚNG: tự mở input từ tệp, tự sở hữu, nên tự đóng.
try (InputStream input = Files.newInputStream(path)) {
    input.transferTo(System.out);
}
// Đã đóng input; System.out vẫn được để mở.
~~~

Đây là **đoạn minh họa** với `path` kiểu `Path` đã khai báo, cần import `java.io.InputStream` và `java.nio.file.Files`, cùng xử lý `IOException`. `transferTo` bản thân nó **không đóng** input hay output. `try-with-resources` ở đây chỉ bao **input do ta sở hữu**, nên không gây đóng `System.out`.

**Quy tắc không thể thay thế bằng mẹo cú pháp:** trước khi dùng `try-with-resources`, hỏi “bên nào sở hữu tài nguyên này và có quyền kết thúc nó?”.

## 9. Sai lầm thường gặp và cách sửa

| Sai lầm | Hệ quả | Cách sửa |
|---|---|---|
| `try (Scanner sc = new Scanner(System.in))` trong hàm đọc một giá trị | Đóng scanner làm đóng input nguồn chung | Dùng scanner chung cấp từ caller; helper chỉ đọc |
| `try (PrintWriter w = new PrintWriter(System.out))` trong hàm in | Khi thoát `try` có thể đóng stdout | Dùng trực tiếp `System.out` hoặc writer được caller quản lý |
| Gọi `System.out.close()` sau một đoạn in | Các phần sau có thể không in được | Nếu chỉ cần đẩy buffer, gọi `flush()` |
| Gọi `System.err.close()` vì tưởng stderr không được dùng nữa | Logging/lỗi tiếp theo có thể mất | Giữ stderr cho tầng quản lý ứng dụng |
| Cho rằng đóng wrapper chỉ giải phóng bộ đệm riêng | Nhiều wrapper còn đóng stream gốc | Kiểm tra hợp đồng `close` của từng lớp |
| Tạo nhiều `Scanner` cùng đọc `System.in` | Buffer đọc trước làm dữ liệu bị giữ trong các scanner khác nhau | Tạo một scanner chung và truyền xuống helper |
| Không đóng `Files.newInputStream` vì sợ đóng stream chuẩn | Rò rỉ file descriptor không liên quan stdout/stdin | Đóng tài nguyên tệp do mình mở; chỉ giữ mở stream được mượn |
| Dùng `close()` thay `flush()` sau mỗi bản ghi | Kết thúc quá sớm nơi nhận dữ liệu | Flush phù hợp, để owner close lúc hoàn tất |
| Giả định `System.out` luôn là màn hình | Khi chuyển hướng, stdout có thể là tệp hoặc pipe | Xem stream theo vai trò kênh I/O |
| Test thay `System.out` rồi không khôi phục | Test khác bị ảnh hưởng bởi global state | Khôi phục tham chiếu gốc trong `finally` |

## 10. Bài tập tự kiểm tra

**Câu 1.** Hàm `askAge()` tạo `Scanner(System.in)` trong `try-with-resources`. Hàm khác tiếp tục cần đọc tên từ `System.in`. Có gì sai?

> Hàm đầu đã **đóng scanner**, kéo theo đóng input nguồn theo hợp đồng của `Scanner`. Tốt hơn tạo một scanner ở tầng điều phối và truyền vào cả hai hàm, không đóng trong các helper.

**Câu 2.** Một helper nhận `OutputStream out` từ caller và bọc `OutputStreamWriter(out, UTF_8)`. Helper có nên gọi `writer.close()` sau mỗi lần ghi?

> Không, trừ khi hợp đồng cho phép helper sở hữu và đóng output. Khi chỉ mượn, có thể gọi `writer.flush()` để đẩy dữ liệu, nhưng đóng writer sẽ đóng luồng bên dưới.

**Câu 3.** Khi nào dùng `try-with-resources` là lựa chọn đúng?

> Khi code **mở và sở hữu** tài nguyên, ví dụ `Files.newInputStream(path)` hoặc `Files.newBufferedWriter(path, UTF_8)`, và sau khi khối kết thúc không còn cần nó. Với stream mượn, quyền close thuộc caller hoặc tầng sở hữu.

**Câu 4.** Chạy `System.out.println("Done")` sau khi một thư viện đã đóng `System.out` mà không thấy lỗi. Điều này có chứng minh stdout còn hoạt động không?

> Không. `PrintStream` có thể ghi nhận lỗi nội bộ thay vì ném `IOException` từ `println`. Cần sửa việc đóng sai stream và, khi chẩn đoán, có thể xem `checkError()`.

**Câu 5.** Tại sao tránh hai `Scanner` độc lập cùng đọc `System.in` ngay cả khi không đóng cái nào?

> Vì mỗi scanner có thể **đọc trước** dữ liệu vào bộ đệm riêng; một scanner có thể đã nhận những byte mà scanner khác dự định đọc. Dùng một scanner chung cho cùng phiên nhập để quản lý thứ tự dữ liệu.

**Câu 6.** Một phương thức mở `InputStream` của file rồi gọi `input.transferTo(System.out)`. Nên đóng stream nào trong phương thức?

> Đóng **input file do phương thức mở**, thường bằng `try-with-resources`. Không tự đóng `System.out` vì đó là stream chuẩn dùng chung; bản thân `transferTo` không đóng stream nào.

## Ghi nhớ

**Stream chuẩn `System.in`, `System.out`, `System.err` là các kênh thường được chia sẻ trong ứng dụng.** Wrapper như `Scanner`, `BufferedReader`, `PrintWriter` có thể **đóng luôn nguồn/đích bên dưới** khi gọi `close()`. Vì vậy hãy:

1. **Đóng** stream do mình tạo và sở hữu (dùng `try-with-resources`).
2. **Không đóng** stream do caller hoặc môi trường cấp nếu chỉ mượn.
3. **Dùng chung một bộ đọc** cho `System.in` khi chương trình nhập nhiều lượt.
4. **Phân biệt `flush` và `close`** khi cần xuất dữ liệu có đệm.

Một API tốt luôn làm rõ **ai sở hữu, ai chỉ dùng, khi nào tài nguyên được đóng**. Đây là chìa khóa để chương trình console, công cụ CLI, thư viện và test Java không vô tình làm hỏng các luồng dùng chung.

**Tài liệu tham khảo:** [Java SE 17 — `System`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html), [`Scanner.close()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Scanner.html#close()), [`PrintStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/PrintStream.html), [`PrintWriter`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/PrintWriter.html).