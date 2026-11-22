# Đóng Scanner và quyền sở hữu luồng nguồn

## 1. Đóng một bộ đọc có thể đóng cả nguồn dữ liệu

Scanner là lớp hỗ trợ đọc và phân tích dữ liệu, nhưng nguồn của nó có thể là tệp, luồng nhập, Reader hoặc String. Vì vậy, gọi `close()` không chỉ liên quan đến biến Scanner đang cầm.

**Khi Scanner đóng, nó gọi đóng nguồn bên dưới nếu nguồn đó thực hiện giao diện Closeable.** Với Scanner bọc InputStream, việc đóng có thể truyền qua lớp Reader trung gian đến luồng byte.

```text
Scanner.close()
    → nguồn đọc Closeable.close()
    → tài nguyên bên dưới được đóng theo hợp đồng của nguồn
```

Câu hỏi cần đặt ra trước khi dùng try-with-resources là: **phạm vi hiện tại có chịu trách nhiệm kết thúc vòng đời của nguồn này không?**

- Nếu tự mở tệp để xử lý trong một phạm vi riêng, thông thường phạm vi đó chịu trách nhiệm đóng.
- Nếu nhận Scanner hoặc luồng dùng chung từ nơi gọi để đọc nhờ, không tự ý đóng.
- Nếu hợp đồng API chuyển giao quyền sở hữu, phải làm theo hợp đồng đó, dù tài nguyên được tạo ở nơi khác.

“Quyền sở hữu” ở đây là trách nhiệm quyết định khi nào tài nguyên hết được sử dụng và ai sẽ đóng nó. Java không tự suy ra quyền này chỉ từ việc truyền tham chiếu vào hàm.

## 2. Hành vi của Scanner.close()

Scanner thực hiện Closeable và dùng được với try-with-resources. Các điểm cần nhớ:

1. Đóng Scanner cũng đóng nguồn nếu nguồn thực hiện Closeable.
2. Gọi `close()` lần nữa trên Scanner đã đóng không có thêm tác dụng.
3. Các thao tác đọc hoặc tìm kiếm như `next()`, `hasNext()`, `nextLine()` trên Scanner đã đóng gây `IllegalStateException`.
4. Không có thao tác mở lại Scanner đã đóng. `reset()` không hồi sinh đối tượng và không mở lại nguồn.

Xem [Scanner.close()](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Scanner.html#close()).

Closeable là giao diện cụ thể mà Scanner kiểm tra với nguồn Readable. Nó là một giao diện con của AutoCloseable; không nên thay điều kiện này bằng suy đoán rằng bất kỳ đối tượng chỉ có AutoCloseable cũng được Scanner tự đóng. Xem [Closeable](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/Closeable.html).

Đóng tài nguyên cũng khác với thu hồi bộ nhớ. Mất tham chiếu đến một Scanner hoặc gán biến thành `null` không phải là cách quản lý việc đóng tệp đúng thời điểm.

## 3. Tự mở tệp: phạm vi sở hữu dùng try-with-resources

Try-with-resources đóng tài nguyên khi thoát khối, kể cả khi bên trong có `return` hoặc ném ngoại lệ trong quá trình thực thi thông thường. Scanner đã được mở thành công sẽ được đóng khi rời phạm vi của nó.

### Chương trình hoàn chỉnh

Lưu thành `OwnedScannerDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;
import java.util.Scanner;

public class OwnedScannerDemo {
    // Hàm này mượn Scanner. Nơi gọi vẫn sở hữu việc đóng.
    private static int sumNumbers(Scanner scanner) throws IOException {
        int sum = 0;
        while (scanner.hasNextInt()) {
            sum += scanner.nextInt();
        }

        if (scanner.ioException() != null) {
            throw scanner.ioException();
        }
        if (scanner.hasNext()) {
            throw new IllegalArgumentException("Invalid number token");
        }
        return sum;
    }

    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("owned-scanner-", ".txt");

        try {
            Files.writeString(file, "10 20\n", StandardCharsets.UTF_8);

            Scanner scanner = new Scanner(file, StandardCharsets.UTF_8)
                    .useLocale(Locale.ROOT);

            try (scanner) {
                System.out.println("sum = " + sumNumbers(scanner));
            }

            try {
                scanner.hasNext();
            } catch (IllegalStateException ex) {
                System.out.println("scanner is closed");
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```shell
javac -encoding UTF-8 OwnedScannerDemo.java
java OwnedScannerDemo
```

Stdout chính xác:

```text
sum = 30
scanner is closed
```

Chương trình tạo và ghi tệp tạm, mở Scanner để đọc, đóng Scanner rồi xóa tệp. `sumNumbers()` chỉ mượn bộ đọc; nó không quyết định vòng đời của tệp.

Cú pháp `try (scanner)` dùng biến đã khai báo và không bị gán lại. Trong mã thông thường, cũng có thể khai báo Scanner ngay trong phần tài nguyên:

```java
try (Scanner scanner = new Scanner(path, StandardCharsets.UTF_8)) {
    int total = sumNumbers(scanner);
    System.out.println(total);
}
```

Đây là đoạn minh họa khi đã có biến Path và các import tương ứng. Hợp đồng try-with-resources được quy định trong [Java Language Specification](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.20.3).

Không chỉ đặt `scanner.close()` ở cuối một khối mã dài: nếu một lệnh phía trước ném ngoại lệ, lệnh close đó có thể không được chạy. Dùng phạm vi tài nguyên để biểu đạt trách nhiệm đóng rõ ràng.

## 4. Quan sát việc đóng lan xuống Reader

Để kiểm chứng, dùng một Reader có bộ đếm số lần đóng. Ví dụ không thao tác với System.in thật nên có thể chạy lặp lại mà không ảnh hưởng nhập liệu của tiến trình.

Lưu thành `ScannerClosePropagationDemo.java`:

```java
import java.io.IOException;
import java.io.StringReader;
import java.util.Scanner;

public class ScannerClosePropagationDemo {
    private static final class TrackingReader extends StringReader {
        private int closeCount;

        private TrackingReader(String text) {
            super(text);
        }

        @Override
        public void close() {
            closeCount++;
            super.close();
        }
    }

    public static void main(String[] args) {
        TrackingReader source = new TrackingReader("7 8");
        Scanner scanner = new Scanner(source);

        System.out.println("first = " + scanner.nextInt());
        scanner.close();
        scanner.close();

        System.out.println("source close count = " + source.closeCount);

        try {
            source.read();
        } catch (IOException ex) {
            System.out.println("reader rejects reads after close");
        }

        try {
            scanner.nextInt();
        } catch (IllegalStateException ex) {
            System.out.println("scanner rejects reads after close");
        }
    }
}
```

Chạy:

```shell
javac -encoding UTF-8 ScannerClosePropagationDemo.java
java ScannerClosePropagationDemo
```

Stdout chính xác:

```text
first = 7
source close count = 1
reader rejects reads after close
scanner rejects reads after close
```

Hai lần gọi `scanner.close()` chỉ truyền việc đóng nguồn một lần. Việc Scanner có thể đã đọc trước ký tự `8` vào bộ đệm không làm nó sử dụng được sau khi bị đóng.

Kết quả Reader từ chối đọc là hành vi của StringReader trong ví dụ. Không phải mọi InputStream đều biểu hiện giống nhau: [ByteArrayInputStream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/ByteArrayInputStream.html) quy định close không có tác dụng và vẫn cho phép đọc sau đó. Vì vậy, không dùng ByteArrayInputStream rồi kết luận “Scanner không đóng nguồn” chỉ vì nguồn vẫn đọc được. Cần kiểm tra đúng hợp đồng nguồn hoặc quan sát lời gọi close như ví dụ trên.

## 5. Mượn Scanner: hàm phụ không tự đóng

Một hàm đọc một trường trong biểu mẫu không nên làm kết thúc cả luồng nhập của biểu mẫu. Hãy truyền một Scanner dùng chung vào các hàm đọc.

Đoạn minh họa sau đọc hai dòng từ Scanner do nơi gọi quản lý:

```java
static int readAge(Scanner input) {
    return Integer.parseInt(input.nextLine().strip());
}

static String readName(Scanner input) {
    return input.nextLine();
}
```

Các hàm này không có try-with-resources quanh `input`. Viết `try (input)` bên trong `readAge()` vẫn sẽ đóng chính đối tượng đó khi hàm kết thúc; nó không tạo một bản sao bộ đọc.

Nơi sở hữu gọi hai hàm theo thứ tự:

```java
int age = readAge(input);
String name = readName(input);
```

Đây là các đoạn minh họa quyền sở hữu, chưa phải toàn bộ xử lý xác thực hoặc EOF của một chương trình tương tác.

Cùng nguyên tắc áp dụng cho API nhận InputStream hoặc Reader từ nơi gọi: cần ghi rõ nguồn là được mượn hay được chuyển giao. Nếu hàm tạo Scanner từ một Reader được mượn rồi đóng Scanner, Reader đó cũng bị đóng. Việc “Scanner do hàm tạo” không tự cho phép hàm kết thúc vòng đời nguồn được mượn.

## 6. System.in thuộc vòng đời của ứng dụng

System.in thường là nguồn nhập dùng chung của tiến trình. Một hàm đọc tuổi, một tác vụ menu hoặc một tiện ích nhỏ không nên tự đóng nó nếu phần khác còn cần nhập tiếp.

```text
Ứng dụng sở hữu nguồn nhập
    → tạo một Scanner
    → các hàm đọc chỉ mượn Scanner
    → ứng dụng quyết định thời điểm kết thúc nhập liệu
```

Đoạn mã sau minh họa việc tạo Scanner khi hợp đồng nguồn nhập là UTF-8:

```java
Scanner input = new Scanner(System.in, StandardCharsets.UTF_8);
int age = readAge(input);
String name = readName(input);
// input còn dùng cho các bước nhập tiếp theo của ứng dụng.
```

Đây là đoạn minh họa trong phạm vi sở hữu của ứng dụng, có các import cần thiết. Việc chọn charset phải phù hợp nguồn stdin thực tế; không mặc định mọi terminal hoặc IDE đều cấp byte UTF-8.

Không đặt try-with-resources quanh Scanner này trong một hàm phụ chỉ để loại cảnh báo của IDE. Cũng không tạo Scanner mới cho từng câu hỏi: nhiều bộ đọc cùng một System.in có thể đọc trước vào các bộ đệm riêng, làm dữ liệu không đến đúng nơi mong đợi.

Ở điểm kết thúc toàn bộ ứng dụng, nếu ứng dụng có quyền đóng và chắc chắn không còn ai đọc, có thể đóng theo chính sách đã chọn. Nguyên tắc không phải “Scanner với System.in tuyệt đối không bao giờ được đóng”; nguyên tắc là **đóng tại đúng phạm vi sở hữu và đúng thời điểm**.

Tạo Scanner mới không mở lại một System.in đã đóng. Nó chỉ bọc lại cùng nguồn đã bị kết thúc.

## 7. Nhiều lớp bọc và nguồn được mở riêng

Với chuỗi Reader bọc InputStream, việc đóng lớp ngoài thường truyền xuống lớp trong. Cần biết hợp đồng của từng lớp bọc, đặc biệt khi dùng thư viện khác.

Nếu chương trình tự mở InputStream và cần bảo đảm nó được đóng ngay cả khi việc tạo Scanner sau đó thất bại, có thể quản lý cả hai trong cùng khai báo tài nguyên:

```java
try (var source = Files.newInputStream(path);
     var scanner = new Scanner(source, StandardCharsets.UTF_8)) {
    // Đọc và xử lý dữ liệu trong phạm vi sở hữu của mình.
}
```

Đây là đoạn minh họa với Path và các import đã có. Khi kết thúc bình thường, các tài nguyên được đóng theo thứ tự ngược khai báo: Scanner trước, source sau. Scanner cũng có thể đã đóng source; việc đóng lặp phải tuân theo hợp đồng của nguồn Closeable. Nếu mở trực tiếp `new Scanner(path, charset)` là đủ cho bài toán, cách đó thường ngắn gọn hơn.

Không cần đặt mọi biến trung gian vào try-with-resources một cách máy móc. Mục đích là biểu đạt đúng phạm vi sở hữu, bao phủ việc khởi tạo có thể thất bại và tránh quên tài nguyên đã mở thành công.

### Lớp bọc không truyền close

Một số ranh giới thư viện buộc phải đóng lớp bọc trong khi nguồn thực vẫn do nơi gọi quản lý. Khi đó có thể thiết kế lớp bọc không truyền close xuống nguồn, với hợp đồng rõ ràng. Ví dụ minh họa khi đã có InputStream `borrowed`:

```java
InputStream view = new FilterInputStream(borrowed) {
    @Override
    public void close() {
        // Nơi gọi vẫn sở hữu borrowed.
    }
};

try (Scanner scanner = new Scanner(view, StandardCharsets.UTF_8)) {
    // Xử lý phần dữ liệu được hợp đồng cho phép.
}
```

Cần import InputStream, FilterInputStream, Scanner và StandardCharsets. [FilterInputStream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/FilterInputStream.html) là lớp bọc luồng có thể được kế thừa để thay đổi hành vi.

Cách này chỉ chặn việc truyền close. Nó **không** ngăn Scanner đọc trước vượt phần ứng dụng vừa lấy, cũng không trả những byte đã đọc vào bộ đệm về nguồn. Nếu cần nhiều giai đoạn cùng đọc một nguồn, ưu tiên một bộ đọc xuyên suốt hoặc một giao thức phân chia dữ liệu rõ ràng. Không xem lớp bọc này là cách tự động làm mọi việc mượn luồng trở nên an toàn.

## 8. Lỗi I/O khi đóng cần được quan sát

Không được suy ra “không có ngoại lệ từ Scanner.close()” là “nguồn chắc chắn đóng thành công”.

Trong triển khai OpenJDK 21, IOException từ thao tác close của nguồn được lưu để lấy qua `scanner.ioException()`; Scanner.close không ném trực tiếp IOException đó. Đây cũng là lý do không chỉ trông chờ ngoại lệ đóng được try-with-resources chuyển ra ngoài. Có thể kiểm tra [triển khai Scanner của OpenJDK](https://raw.githubusercontent.com/openjdk/jdk21u/master/src/java.base/share/classes/java/util/Scanner.java).

### Chương trình hoàn chỉnh

Lưu thành `ScannerCloseFailureDemo.java`:

```java
import java.io.IOException;
import java.io.Reader;
import java.util.Scanner;

public class ScannerCloseFailureDemo {
    private static final class FailingCloseReader extends Reader {
        @Override
        public int read(char[] buffer, int offset, int length) {
            return length == 0 ? 0 : -1;
        }

        @Override
        public void close() throws IOException {
            throw new IOException("close failed");
        }
    }

    public static void main(String[] args) {
        Scanner scanner = new Scanner(new FailingCloseReader());

        try (scanner) {
            System.out.println("has token = " + scanner.hasNext());
        }

        IOException failure = scanner.ioException();
        System.out.println("close error recorded = " + (failure != null));
        if (failure != null) {
            System.out.println("message = " + failure.getMessage());
        }
    }
}
```

Chạy:

```shell
javac -encoding UTF-8 ScannerCloseFailureDemo.java
java ScannerCloseFailureDemo
```

Stdout chính xác:

```text
has token = false
close error recorded = true
message = close failed
```

Đây là nguồn giả lập lỗi đóng để quan sát cơ chế, không phải Reader dùng trong sản phẩm. Với tác vụ cần độ tin cậy cao, kiểm tra lỗi đọc trong quá trình hoàn tất xử lý và quan sát lỗi sau khi đóng; `ioException()` chỉ giữ IOException gần nhất, không phải danh sách tất cả lỗi.

Lỗi định dạng như InputMismatchException là một loại khác. Nó không tự biến thành lỗi I/O và không được lấy qua ioException.

## 9. Những nhầm lẫn thường gặp

| Cách nghĩ | Cách quyết định đúng hơn |
| --- | --- |
| Hàm tạo Scanner thì luôn được đóng Scanner | Xem việc đóng có ảnh hưởng nguồn được mượn không |
| Hàm nhận Scanner thì có thể đóng sau khi đọc xong phần mình | Chỉ đóng nếu hợp đồng chuyển quyền sở hữu |
| Tạo Scanner mới sẽ sửa được lỗi nguồn bị đóng | Nguồn đã đóng không được mở lại bằng lớp bọc mới |
| Dùng try-with-resources ở mọi hàm là đủ | Phạm vi tài nguyên phải phù hợp quyền sở hữu |
| GC sẽ đóng tệp đúng lúc | Chủ sở hữu phải đóng tài nguyên theo vòng đời xác định |
| Đọc đến EOF là đã gọi close | Hết dữ liệu và kết thúc tài nguyên là hai trạng thái khác nhau |
| Nguồn còn đọc được sau close chứng minh không hề đóng | Một số nguồn trong bộ nhớ có close không gây mất khả năng đọc |

## 10. Tự kiểm tra thiết kế

1. Trong ví dụ tệp, nếu `sumNumbers()` ném ngoại lệ, Scanner vẫn được đóng nhờ phạm vi try-with-resources.
2. Nếu chuyển try-with-resources vào một hàm chỉ đọc trường tuổi rồi còn đọc tên ở bên ngoài, nguồn đã bị kết thúc quá sớm.
3. Với Reader được mượn từ nơi gọi, ghi rõ ai được quyền đóng trước khi bọc bằng Scanner.
4. Với lớp bọc không truyền close, kiểm tra cả vấn đề đọc trước; ngăn đóng nguồn không bảo đảm phần dữ liệu chưa tiêu thụ được giữ nguyên cho bộ đọc khác.
5. Dùng bộ đếm close trong ví dụ để phân biệt việc Scanner gọi đóng nguồn với hành vi cụ thể của nguồn sau đóng.

Một thiết kế rõ ràng có một nơi chịu trách nhiệm vòng đời nguồn, các hàm đọc có hợp đồng mượn/chuyển giao cụ thể, và thao tác đóng diễn ra khi toàn bộ người sử dụng hợp lệ đã hoàn tất.
