# Scanner: nguồn String, Readable, luồng vào và tệp

## 1. Một bộ phân tích, nhiều nguồn văn bản

`Scanner` thuộc `java.util`, dùng để tách văn bản thành các đơn vị dữ liệu (token) và chuyển chúng sang kiểu như `int` hoặc `double`. Trước khi gọi `nextInt()` hay `nextLine()`, ta phải trả lời: **văn bản đến từ đâu, đã là ký tự chưa, và ai chịu trách nhiệm đóng nguồn?**

Ví dụ, cùng văn bản `"10 20 30"` có thể nằm trong một `String`, một đối tượng đọc ký tự, luồng byte hoặc tệp. Quy tắc tách token không đổi chỉ vì nguồn đổi; phần khác nhau nằm ở cách cung cấp ký tự, giải mã byte và quản lý tài nguyên.

Có hai đường đi chính:

~~~text
String / Readable ────────────────────────> ký tự ──> Scanner ──> token / số
InputStream / tệp ──> giải mã theo Charset ──> ký tự ──> Scanner ──> token / số
~~~

`Charset` là bảng mã dùng để chuyển byte thành ký tự. Không thể sửa việc giải mã sai bằng cách đổi dấu phân cách hoặc gọi `useLocale()`: bảng mã xử lý byte; locale xử lý quy ước biểu diễn số.

Các ví dụ dùng Java 17 trở lên, với API vẫn được sử dụng hiện nay. Tên module Java 5 nói về bối cảnh xuất hiện của `Scanner`, không buộc chương trình hiện tại dùng cách mở tệp hoặc quản lý tài nguyên cũ.

## 2. Chọn nguồn đúng với dữ liệu đang có

| Dữ liệu đang có | Cách tạo thường dùng | Điều cần quyết định |
| --- | --- | --- |
| Văn bản trong bộ nhớ | `new Scanner(text)` | Đây là nội dung, không phải đường dẫn |
| Nguồn ký tự, như `StringReader` hoặc `BufferedReader` | `new Scanner(readable)` | Nguồn đã giải mã; ai sở hữu nguồn? |
| Luồng byte | `new Scanner(input, charset)` | Chọn đúng bảng mã; đóng luồng theo quyền sở hữu |
| Đường dẫn tệp | `new Scanner(path, charset)` | Lỗi mở tệp, bảng mã và đóng tài nguyên |
| Đối tượng `File` từ API có sẵn | `new Scanner(file, charset)` | `File` vẫn là API hợp lệ; không cần chuyển qua lại chỉ để đọc |

Các lời gọi trong bảng là mảnh mã minh họa, cần biến và import tương ứng. `Path` là lựa chọn thuận tiện cho mã mới khi đang làm việc với `java.nio.file.Files`.

Một lỗi rất dễ gặp:

~~~java
Scanner scanner = new Scanner("data.txt");
~~~

Lệnh trên tạo bộ phân tích cho chính tám ký tự `data.txt`. Nó **không mở tệp**. Nếu muốn đọc tệp, truyền một `Path`:

~~~java
Scanner scanner = new Scanner(Path.of("data.txt"), StandardCharsets.UTF_8);
~~~

Mảnh mã thứ hai cần xử lý `IOException` và đóng scanner khi hoàn tất. Nếu dùng đường dẫn tương đối, vị trí được xác định theo thư mục làm việc của tiến trình; vị trí tệp mã nguồn không quyết định điều đó.

## 3. Nguồn String: đầu vào đã là văn bản

`String` phù hợp khi dữ liệu đã được đọc hoặc tạo trong bộ nhớ: chuỗi nhập thử, nội dung một bản tin nhỏ hay dữ liệu kiểm thử. Không cần mã hóa thành byte rồi giải mã trở lại chỉ để đưa vào `Scanner`.

~~~java
try (Scanner scanner = new Scanner("12 34")) {
    int first = scanner.nextInt();
    int second = scanner.nextInt();
    System.out.println(first + second);
}
~~~

Đây là mảnh mã đặt trong một phương thức, với `import java.util.Scanner;`; kết quả là `46`.

Một `String` có thể chứa xuống dòng và nhiều token. `Scanner` đọc dần từ vị trí hiện tại của nó; gọi một phương thức đọc không làm thay đổi chuỗi gốc. Khi cần đọc lại từ đầu, tạo một scanner mới. `reset()` đặt lại cấu hình phân tích, không đưa vị trí đọc trở về đầu dữ liệu.

Nguồn chuỗi không chờ người dùng nhập. Khi hết nội dung, kiểm tra thích hợp như `hasNext()` hoặc `hasNextLine()` trả về `false`. Gọi `next()` khi không còn token sẽ gây `NoSuchElementException`.

## 4. Readable: hợp đồng cung cấp ký tự

`Readable` là giao diện ở `java.lang` mô tả một nguồn ký tự thông qua phương thức:

~~~java
int read(java.nio.CharBuffer target) throws java.io.IOException;
~~~

Đây là chữ ký phương thức, không phải một chương trình độc lập. Nguồn đưa ký tự vào vùng đệm được truyền vào, trả số ký tự đã cung cấp hoặc `-1` khi kết thúc. Không được suy ra kết thúc chỉ từ giá trị `0`.

Những đối tượng quen thuộc có thể truyền vào `Scanner(Readable)` gồm:

- `StringReader`: đọc từ một chuỗi.
- `BufferedReader`: đọc ký tự có bộ đệm, chẳng hạn từ `Files.newBufferedReader(...)`.
- `InputStreamReader`: chuyển byte thành ký tự bằng bảng mã đã chọn.
- `CharBuffer`: cung cấp các ký tự còn lại trong vùng đệm.

`Reader` là một lớp trừu tượng triển khai `Readable`; hai tên này không đồng nghĩa. Một đối tượng tự triển khai `Readable` không bắt buộc phải là `Reader` và không tự nhiên trở thành tài nguyên có thể đóng.

`String` cũng không triển khai `Readable`: `Scanner(String)` là một hàm khởi tạo riêng. Do đó, `new Scanner(text)` và `new Scanner(new StringReader(text))` có thể cho cùng kết quả nhưng đi qua hai loại đầu vào khác nhau.

Với một `Readable` đã cung cấp ký tự, `Scanner` không có thêm bước chọn bảng mã. Nếu cần đọc tệp UTF-8 qua `BufferedReader`, bảng mã phải được chọn lúc mở reader:

~~~java
try (Scanner scanner = new Scanner(
        Files.newBufferedReader(path, StandardCharsets.UTF_8))) {
    while (scanner.hasNextLine()) {
        System.out.println(scanner.nextLine());
    }
}
~~~

Mảnh mã này cần `Path path`, các import tương ứng và xử lý `IOException`. Reader được tạo cho riêng scanner; đóng scanner cũng đóng reader.

Một nguồn `Readable` không nhất thiết là toàn bộ dữ liệu có sẵn ngay lập tức. Chẳng hạn reader nối với một luồng có thể phải chờ dữ liệu. Giao diện chung không bảo đảm việc đọc không chặn.

### Khi dùng CharBuffer

`Scanner` lấy phần dữ liệu từ `position` đến `limit` của `CharBuffer`. Với `CharBuffer.wrap("10 20")`, vùng đọc đã được đặt sẵn. Nếu tự tạo vùng đệm rồi `put(...)`, cần chuyển sang chế độ đọc bằng `flip()`:

~~~java
CharBuffer buffer = CharBuffer.allocate(20);
buffer.put("10 20");
buffer.flip();

try (Scanner scanner = new Scanner(buffer)) {
    System.out.println(scanner.nextInt() + scanner.nextInt());
}
~~~

Đây là mảnh mã trong phương thức, cần import `java.nio.CharBuffer` và `java.util.Scanner`; kết quả là `30`. Quên `flip()` khiến vùng dữ liệu được đọc không phải phần vừa ghi.

Không thay đổi vị trí hoặc nội dung vùng đệm từ nơi khác khi scanner đang sử dụng nó.

## 5. InputStream: luồng byte cần được giải mã

`InputStream` cung cấp byte, không trực tiếp cung cấp ký tự. Nó có thể là luồng từ tệp, bộ nhớ hoặc `System.in`. Với dữ liệu được quy định là UTF-8, truyền bảng mã rõ ràng:

~~~java
new Scanner(input, StandardCharsets.UTF_8)
~~~

Đây là biểu thức tạo đối tượng với `InputStream input` đã có; mã thực tế còn phải quản lý việc đóng.

Đừng chọn UTF-8 chỉ vì máy phát triển của mình hiển thị đúng. Cần biết bên tạo dữ liệu đã dùng bảng mã nào. Khi nhận được một `Reader`, công đoạn này đã diễn ra trước `Scanner`; còn khi nhận `InputStream`, nó vẫn cần được quyết định.

Đầu vào tương tác có thêm hai vấn đề:

1. `System.in` thường được dùng chung trong cả chương trình. Đóng scanner bọc nó có thể làm các phần khác không đọc tiếp được.
2. `hasNext()` có thể chờ dữ liệu hoặc dấu hiệu kết thúc. `false` biểu thị không còn token; nó không có nghĩa “hiện tại người dùng chưa gõ gì”.

Trong mã JDK hiện đại đọc trực tiếp `System.in`, bảng mã của đầu vào chuẩn có thể khác bảng mã mặc định. Cần theo cấu hình của môi trường chạy, thay vì giả định bảng mã của tệp cũng đúng cho terminal. Chương trình chạy trên Java 17 cũng không nên giả định thuộc tính `stdin.encoding` luôn tồn tại.

Một mẫu tổ chức quyền sở hữu thường phù hợp là tạo **một scanner đầu vào ở biên của chương trình**, truyền nó cho những phương thức cần đọc và để nơi tạo quyết định thời điểm đóng. Không tạo rồi đóng một scanner mới trong mỗi phương thức dùng chung `System.in`.

Không dùng đồng thời hai scanner hoặc trộn `input.read()` với `scanner.next()` trên cùng luồng: scanner có thể đã đọc trước vào bộ đệm. Phần byte mà nơi khác tưởng còn trong nguồn có thể đã nằm trong scanner.

## 6. Tệp: Path, bảng mã và vòng đời

Nếu mục tiêu là phân tích token trong tệp, có thể tạo scanner trực tiếp từ `Path`. Nếu cần một chuỗi xử lý ký tự đã có reader, dùng `Scanner(Readable)`. Không cần `Files.readString(...)` trước chỉ để scanner đọc được tệp: bước đó nạp toàn bộ văn bản vào bộ nhớ.

Khối `try-with-resources` đóng scanner khi thoát khối, kể cả khi phần xử lý bên trong ném ngoại lệ. Theo hợp đồng của `Scanner`, việc đóng được chuyển xuống nguồn nếu nguồn triển khai `Closeable`. Vì thế, quyết định đóng liên quan đến **quyền sở hữu nguồn**, không chỉ liên quan đến cú pháp ngắn gọn. [Tham khảo hợp đồng Scanner](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Scanner.html).

Một `Path` chỉ mô tả vị trí; nó không chứng minh tệp tồn tại hay đọc được. Việc mở tệp có thể thất bại vì đường dẫn không đúng, thiếu quyền hoặc lỗi hệ thống tệp. Không biến những lỗi đó thành “tệp rỗng” bằng cách bỏ qua ngoại lệ.

Nếu yêu cầu chỉ là đọc từng dòng, `BufferedReader` hoặc `Files.lines(...)` cũng là lựa chọn hiện hành. `Scanner` hữu ích khi cần tách và chuyển đổi token tiện lợi; không mặc nhiên là lựa chọn nhanh nhất cho mọi tệp lớn.

## 7. Chương trình chạy đầy đủ: cùng dữ liệu qua bốn nguồn

Lưu thành `ScannerSourcesDemo.java`. Chương trình tự tạo tệp tạm, đọc cùng dãy số ở bốn nguồn và xóa tệp trong `finally`. Không cần chuẩn bị tệp hay nhập bàn phím.

~~~java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.StringReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Scanner;

public class ScannerSourcesDemo {
    private static int sum(Scanner scanner) throws IOException {
        int total = 0;

        while (scanner.hasNext()) {
            if (!scanner.hasNextInt()) {
                throw new IllegalArgumentException(
                        "Invalid integer: " + scanner.next());
            }
            total = Math.addExact(total, scanner.nextInt());
        }

        IOException failure = scanner.ioException();
        if (failure != null) {
            throw failure;
        }
        return total;
    }

    public static void main(String[] args) throws IOException {
        String text = "10 20 30";

        try (Scanner scanner = new Scanner(text)) {
            System.out.println("String: " + sum(scanner));
        }

        try (Scanner scanner = new Scanner(new StringReader(text))) {
            System.out.println("Readable: " + sum(scanner));
        }

        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        try (Scanner scanner = new Scanner(
                new ByteArrayInputStream(bytes),
                StandardCharsets.UTF_8)) {
            System.out.println("InputStream: " + sum(scanner));
        }

        Path file = Files.createTempFile("scanner-source-", ".txt");
        try {
            Files.writeString(file, text, StandardCharsets.UTF_8);
            try (Scanner scanner = new Scanner(
                    file, StandardCharsets.UTF_8)) {
                System.out.println("Path: " + sum(scanner));
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp:

~~~shell
javac --release 17 -encoding UTF-8 ScannerSourcesDemo.java
java ScannerSourcesDemo
~~~

Stdout chính xác:

~~~text
String: 60
Readable: 60
InputStream: 60
Path: 60
~~~

Quan sát từ chương trình:

- `sum(...)` không biết dữ liệu ban đầu là chuỗi hay tệp. Nó nhận một scanner đã được cấu hình.
- Khối tạo nguồn quyết định cách mở và đóng; hàm tính tổng chỉ dùng scanner được truyền vào.
- `ByteArrayInputStream` chứa byte được tạo bằng UTF-8; scanner dùng đúng UTF-8 để giải mã.
- Nhánh `Path` cho thấy việc mở tệp và phân tích token có thể làm trực tiếp, không cần đọc toàn bộ tệp thành chuỗi.
- Khi gặp token không phải số nguyên, chương trình báo dữ liệu không hợp lệ thay vì lặng lẽ chấp nhận tổng của một phần đầu.
- `Math.addExact` báo tràn số, tránh kết quả tổng bị quay vòng âm/dương mà người đọc không nhận ra.

## 8. Phân biệt kết thúc nguồn, lỗi I/O và token sai

Ba tình huống cần được xử lý riêng:

| Tình huống | Cách nhận diện | Cách nghĩ phù hợp |
| --- | --- | --- |
| Hết dữ liệu bình thường | Không còn token/dòng và `ioException()` là `null` | Đã đọc đến cuối |
| Đọc nguồn gặp `IOException` | `scanner.ioException()` khác `null` | Dữ liệu nhận được có thể mới là một phần |
| Token không khớp kiểu cần đọc | `hasNextInt()` là `false` dù còn token, hoặc `nextInt()` ném `InputMismatchException` | Dữ liệu không đúng định dạng mong đợi |

Đặc điểm cần nhớ: `Scanner` không chuyển mọi lỗi đọc thành `IOException` ném trực tiếp từ `next()`. Với lỗi I/O ở nguồn đọc, scanner xem như nguồn đã kết thúc và lưu lỗi để lấy bằng `ioException()`. Điều này khác lỗi xảy ra lúc mở tệp trong hàm khởi tạo. [Tài liệu Scanner về lỗi nguồn](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Scanner.html).

Vì vậy, vòng lặp đọc hết token chưa đủ để khẳng định tệp đã được đọc thành công toàn bộ. Với dữ liệu quan trọng, kiểm tra `ioException()` trước khi chấp nhận kết quả.

### Thí nghiệm lỗi đọc và việc đóng nguồn

Lưu thành `ScannerFailureDemo.java`:

~~~java
import java.io.Closeable;
import java.io.IOException;
import java.nio.CharBuffer;
import java.util.Scanner;

public class ScannerFailureDemo {
    private static final class BrokenSource
            implements Readable, Closeable {
        private boolean delivered;
        private boolean closed;

        @Override
        public int read(CharBuffer target) throws IOException {
            if (!delivered) {
                delivered = true;
                target.put('7');
                target.put(' ');
                return 2;
            }
            throw new IOException("simulated read failure");
        }

        @Override
        public void close() {
            closed = true;
        }
    }

    public static void main(String[] args) {
        BrokenSource source = new BrokenSource();

        try (Scanner scanner = new Scanner(source)) {
            System.out.println("value=" + scanner.nextInt());
            System.out.println("more=" + scanner.hasNext());
            IOException failure = scanner.ioException();
            System.out.println("error=" + failure.getMessage());
        }

        System.out.println("closed=" + source.closed);
    }
}
~~~

Đây là nguồn giả lập nhỏ để quan sát hợp đồng, không phải bộ đọc dùng cho hệ thống thực tế. Chương trình luôn đưa vào vùng đệm hai ký tự ở lần đọc đầu rồi mô phỏng lỗi ở lần đọc sau.

~~~shell
javac --release 17 -encoding UTF-8 ScannerFailureDemo.java
java ScannerFailureDemo
~~~

Stdout chính xác:

~~~text
value=7
more=false
error=simulated read failure
closed=true
~~~

`more=false` đứng một mình không phân biệt được hết dữ liệu bình thường với nguồn lỗi. Dòng `error=...` cung cấp bằng chứng lỗi đọc; `closed=true` cho thấy scanner đã đóng nguồn triển khai `Closeable`.

Nguồn tự viết trong ứng dụng thực tế còn phải tuân thủ dung lượng còn lại của `CharBuffer`, không ghi quá chỗ trống và trả `-1` khi thực sự kết thúc. `Readable` tự nó không có phương thức `close()`. [Hợp đồng Readable.read](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Readable.html).

## 9. Các lỗi chọn nguồn thường gặp

### Truyền tên tệp như chuỗi nội dung

`new Scanner("orders.txt")` phân tích tên tệp. Dùng `Path.of("orders.txt")` để yêu cầu mở tệp.

### Giải mã hai lần không cần thiết

Khi đã có `Reader` đúng bảng mã, truyền nó trực tiếp. Việc chuyển văn bản sang byte rồi tạo scanner với bảng mã khác có thể làm hỏng dữ liệu và khiến luồng xử lý khó theo dõi.

### Cho rằng đổi nguồn sẽ sửa lỗi trộn token và dòng

Sau `nextInt()`, `nextLine()` đọc phần còn lại của dòng hiện tại. Quy tắc này không tự đổi khi chuyển từ `String` sang tệp hoặc bàn phím. Phải chọn rõ cách phân tích theo token hay theo dòng; đây là quyết định độc lập với nguồn.

### Đóng nguồn mà nơi khác còn sử dụng

Đóng scanner bọc `Reader` hoặc `System.in` có thể đóng tài nguyên dùng chung. Nơi tạo và sở hữu tài nguyên phải thống nhất vòng đời; không đóng tùy tiện trong một hàm hỗ trợ.

### Xem hasNext() là phép kiểm tra không chờ

Với tệp và chuỗi hữu hạn, việc đọc thường nhanh và kết thúc rõ ràng. Với đầu vào tương tác hoặc nguồn đang truyền dữ liệu, thao tác có thể chặn. Không dùng `Scanner` như cơ chế thăm dò không chặn.

### Đọc một phần dữ liệu rồi kết luận thành công

`while (scanner.hasNextInt())` dừng cả khi gặp token sai. Nếu yêu cầu mọi token phải là số nguyên, kiểm tra còn token không hợp lệ và lỗi I/O như trong `sum(...)`.

### Đọc toàn bộ tệp vào String theo thói quen

Với tệp lớn, việc tạo một chuỗi chứa toàn bộ nội dung làm tăng bộ nhớ cần giữ. Khi chỉ cần duyệt tuần tự, mở nguồn và đọc dần. Scanner vẫn có bộ đệm riêng và một số kiểu tìm kiếm có thể giữ nhiều dữ liệu; không suy ra bộ nhớ luôn cố định.

## 10. Tự thực hành

1. Thay `text` của `ScannerSourcesDemo` bằng `"10 20 x"`. Dự đoán chỗ báo lỗi và vì sao chương trình không in bốn dòng tổng thành công.
2. Tạo nguồn `CharBuffer.wrap("10 20 30")` rồi truyền vào `sum(...)`. Kiểm tra tổng vẫn là `60` mà không chọn bảng mã.
3. Đổi nguồn byte sang `"cà phê 42".getBytes(StandardCharsets.UTF_8)`. Dùng `next()` hai lần rồi `nextInt()`, giải thích vì sao hai từ có dấu được đọc đúng.
4. Trong `ScannerFailureDemo`, thay lỗi đọc ở lần sau bằng `return -1;` và sửa phần in lỗi thành kiểm tra null. Đối chiếu kết thúc bình thường với kết thúc vì lỗi.
5. Thiết kế hàm nhận một scanner bàn phím do bên gọi truyền vào. Ghi rõ ai tạo và ai đóng nguồn, rồi kiểm tra hàm có thể được gọi hai lần.

Điểm cần tự giải thích được là: **nguồn cung cấp dữ liệu, bảng mã chuyển byte thành ký tự, Scanner phân tích văn bản, còn vòng đời thuộc về nơi sở hữu tài nguyên.**
