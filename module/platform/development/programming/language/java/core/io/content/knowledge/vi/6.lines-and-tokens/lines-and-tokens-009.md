# Scanner.ioException và đóng nguồn dữ liệu trong Java

`java.util.Scanner` giúp đọc dữ liệu văn bản thành **token**, số, chuỗi hoặc dòng. Tuy nhiên, một chương trình đọc dữ liệu thực tế còn phải phân biệt **hết dữ liệu hợp lệ (EOF)** với **lỗi I/O**, và phải biết **ai chịu trách nhiệm đóng nguồn** sau khi đọc xong. Hai điểm này dễ bị bỏ sót vì `Scanner` chủ động xử lý một số `IOException` của nguồn dữ liệu thay cho người gọi.

Bài này tập trung vào `Scanner.ioException()`, `Scanner.close()`, vòng đời nguồn `Readable`/`Closeable` và mẫu mã xử lý lỗi phù hợp cho file, input stream, reader và bàn phím. Ví dụ sử dụng Java 17+.

## 1. Scanner nằm ở đâu trong luồng đọc?

Một pipeline thường có dạng:

```text
Tệp / socket / System.in / nguồn byte
               |
               v
       InputStream / Reader
               |
               | đọc dữ liệu, có thể phát sinh IOException
               v
             Scanner
        tách token, parse số,
        xử lý dấu phân cách
               |
               v
      hasNext(), next(), nextInt(),
      hasNextLine(), nextLine(), ...
```

`Scanner` có thể được tạo trực tiếp từ `Readable` (ví dụ `Reader`), `InputStream`, `File`, `Path`, `String` và các dạng nguồn khác. Cách dùng nào phù hợp tùy nguồn và nhu cầu mã hóa ký tự. Khi nguồn là byte, nên chọn **charset tường minh**, chẳng hạn `StandardCharsets.UTF_8`, để nội dung văn bản được giải mã nhất quán.

Một số tình huống lỗi khác nhau:

| Tình huống | Dấu hiệu thông thường |
| --- | --- |
| Dữ liệu hết tự nhiên | `hasNext()` / `hasNextLine()` trở thành `false` |
| Nguồn `Readable.read(...)` ném `IOException` | Scanner xem như đến cuối đầu vào; nguyên nhân có thể xem bằng `ioException()` |
| Token có mặt nhưng sai kiểu số | `nextInt()` có thể ném `InputMismatchException` |
| Gọi `next()` khi không còn token | `NoSuchElementException` |
| Gọi thao tác tìm/đọc khi Scanner đã đóng | `IllegalStateException` |
| Mở tệp thất bại tại constructor | Constructor có thể ném `IOException` / `FileNotFoundException` trước khi có Scanner để kiểm tra |
| Đóng nguồn `Closeable` thất bại | `Scanner.close()` xử lý lỗi và có thể lưu `IOException` để truy vấn qua `ioException()` |

Không nên gộp các tình huống này thành “Scanner trả false là thành công” hoặc “bất kỳ exception nào cũng là lỗi file”.

## 2. Chính xác Scanner.ioException() làm gì?

Chữ ký:

```java
public IOException ioException()
```

Đây là một phương thức **truy vấn**, không phải lệnh đọc dữ liệu:

- Trả về **`IOException` gần nhất** mà Scanner ghi nhận từ nguồn `Readable` bên dưới.
- Trả về `null` nếu chưa có ngoại lệ I/O thuộc loại đó được ghi nhận.
- Không tự ném lại ngoại lệ. Bạn phải kiểm tra giá trị trả về và quyết định báo lỗi, ghi log, thử lại hay dừng.
- Có thể gọi sau khi đọc xong và cả **sau `close()`** để xem lỗi đóng nguồn.
- Nó **không** đại diện cho mọi loại lỗi parse, sai định dạng dữ liệu hoặc lỗi ở constructor tạo nguồn.

Theo hợp đồng API Java 17, nếu phương thức `read()` trên `Readable` bên dưới ném `IOException`, Scanner **giả định đã đến cuối đầu vào**. Vì vậy, một vòng lặp `while (scanner.hasNext())` có thể dừng bình thường dù bên dưới vừa xảy ra lỗi I/O. Phải hỏi `ioException()` mới phân biệt được trong trường hợp này.

### Ví dụ tư duy: đọc được hai token rồi lỗi

```text
Nguồn thực tế: "10 20" + [IOException khi lấy dữ liệu tiếp]
                            |
                            v
Scanner có thể cung cấp "10", "20" trước, sau đó hasNext() == false.
                                  |
                                  +--- ioException() != null
                                       -> nguồn bị lỗi; không coi dữ liệu là đầy đủ.
```

Số token được trả trước khi lỗi phụ thuộc cơ chế đọc trước (buffering), quy tắc delimiter và thời điểm nguồn ném ngoại lệ; **không** dự đoán rằng sẽ nhận chính xác hai token trong mọi nguồn bằng một sơ đồ. Điều quan trọng là **không kết luận thành công chỉ từ việc vòng lặp token kết thúc**.

`ioException() == null` chỉ có nghĩa Scanner **chưa ghi nhận `IOException` từ nguồn**. Nó không chứng minh dữ liệu hợp lệ về nghiệp vụ, đủ số trường, đúng checksum, đúng charset, hay toàn bộ file mong đợi đã đến.

## 3. Vì sao IOException có thể không xuất hiện trực tiếp ở hasNext()/next()?

`Scanner` phục vụ thao tác phân tích văn bản và token. Nó quản lý đọc từ `Readable` và có lựa chọn thiết kế: **chuyển lỗi đọc thuộc `IOException` thành tín hiệu giống EOF ở tầng token**, đồng thời giữ lại nguyên nhân để truy vấn sau.

Ví dụ cách dùng **chưa đủ an toàn**:

```java
try (Scanner scanner = new Scanner(source)) {
    while (scanner.hasNext()) {
        process(scanner.next());
    }
    // Không kiểm tra scanner.ioException():
    // một read IOException có thể vừa làm vòng lặp kết thúc.
}
```

Đây là mảnh mã: `source` là một nguồn `Readable` hợp lệ và `process` là hàm nghiệp vụ. Nếu xử lý dữ liệu quan trọng, phải kiểm tra lỗi I/O **sau khi đọc**, và nếu cần nhận biết lỗi đóng nguồn thì kiểm tra **sau khi đóng**.

Để không nhầm:

- `hasNext() == false` có thể nghĩa không còn token; cần kiểm tra `ioException()` trước khi tuyên bố một luồng đã được đọc đầy đủ.
- `hasNextInt() == false` có thể nghĩa token kế tiếp không phải số nguyên theo locale/radix hiện tại, hoặc không còn token, hoặc lỗi đọc bên dưới. Cần kiểm tra ngữ cảnh; riêng `ioException()` chỉ trả lời về I/O.
- `nextInt()` có thể ném `InputMismatchException` nếu token sai kiểu. Ngoại lệ này **không** được ánh xạ tự động thành `ioException()`.
- `next()`/`nextLine()` có thể ném `NoSuchElementException` khi không còn nội dung phù hợp. Không nên chỉ bắt ngoại lệ đó rồi mặc định nguồn đã hết bình thường.

## 4. Ví dụ Java 17+ chạy được: đọc lỗi, đóng lỗi và vòng đời

Tệp `ScannerIoLifecycleDemo.java` dưới đây có hai nguồn mô phỏng, tạo lỗi có kiểm soát. Ví dụ không cần tệp trên đĩa nên kết quả dễ tái lập.

```java
import java.io.Closeable;
import java.io.IOException;
import java.nio.CharBuffer;
import java.util.Scanner;

public class ScannerIoLifecycleDemo {
    private static final class FaultyReadSource
            implements Readable, Closeable {
        int closeCalls;

        @Override
        public int read(CharBuffer target) throws IOException {
            throw new IOException("read failed");
        }

        @Override
        public void close() {
            closeCalls++;
        }
    }

    private static final class FaultyCloseSource
            implements Readable, Closeable {
        int closeCalls;

        @Override
        public int read(CharBuffer target) {
            return -1; // EOF tự nhiên
        }

        @Override
        public void close() throws IOException {
            closeCalls++;
            throw new IOException("close failed");
        }
    }

    public static void main(String[] args) {
        // 1. Nguồn không lỗi; Scanner đọc đủ hai số.
        Scanner normal = new Scanner("7 11");
        int sum = 0;
        while (normal.hasNextInt()) {
            sum += normal.nextInt();
        }
        System.out.println("normal sum: " + sum);
        System.out.println("normal ioException: " + normal.ioException());
        normal.close();

        // 2. Nguồn ném IOException ngay lần đọc đầu tiên.
        FaultyReadSource reader = new FaultyReadSource();
        Scanner readScanner = new Scanner(reader);
        System.out.println("read hasNext: " + readScanner.hasNext());
        System.out.println("read ioException: "
                + readScanner.ioException().getMessage());
        readScanner.close();
        System.out.println("read close calls: " + reader.closeCalls);

        // 3. Nguồn hết tự nhiên nhưng đóng nguồn lại ném IOException.
        FaultyCloseSource closer = new FaultyCloseSource();
        Scanner closeScanner = new Scanner(closer);
        System.out.println("close error before close: "
                + closeScanner.ioException());
        closeScanner.close();
        System.out.println("close error after close: "
                + closeScanner.ioException().getMessage());
        System.out.println("close attempts: " + closer.closeCalls);

        try {
            closeScanner.hasNext();
        } catch (IllegalStateException e) {
            System.out.println("closed scanner: "
                    + e.getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy với Java 17+:

```bash
javac ScannerIoLifecycleDemo.java
java ScannerIoLifecycleDemo
```

Stdout đã kiểm tra bằng JDK:

```text
normal sum: 18
normal ioException: null
read hasNext: false
read ioException: read failed
read close calls: 1
close error before close: null
close error after close: close failed
close attempts: 1
closed scanner: IllegalStateException
```

Những điểm cần rút ra:

1. Nguồn chuỗi thông thường không có `IOException`, nên `normal.ioException()` trả `null`.
2. `readScanner.hasNext()` trở thành `false` dù nguyên nhân là **`IOException("read failed")`**, không phải EOF thật. Lỗi được lưu trong `ioException()`.
3. Khi `readScanner.close()` được gọi, Scanner gọi `close()` của `FaultyReadSource` đúng một lần vì nó thực thi `Closeable`.
4. `FaultyCloseSource.read()` trả `-1` (EOF thật). Trước khi đóng, `ioException()` là `null`; sau khi đóng lỗi, `ioException()` mang `"close failed"`.
5. `Scanner.close()` không khai báo `throws IOException`; lỗi close của nguồn bị xử lý bên trong và có thể phải truy xuất bằng `ioException()`.
6. Sau `close()`, thao tác tìm token như `hasNext()` ném `IllegalStateException`. Lưu tham chiếu đến Scanner chỉ để kiểm tra lỗi sau close, không dùng nó để đọc tiếp.

Đây là **mô phỏng có chủ ý** chứ không phải ví dụ về lỗi hệ điều hành thực. Tình huống thực tế có thể là lỗi ổ đĩa, ngắt kết nối mạng, nguồn đọc được một phần rồi thất bại, hoặc lỗi xảy ra trong lúc đóng tài nguyên.

## 5. Đóng Scanner: đóng cả nguồn khi nguồn là Closeable

`Scanner` hiện thực `Closeable` và `AutoCloseable`; có thể dùng trong `try-with-resources`.

Hợp đồng `Scanner.close()`:

- Khi Scanner còn mở, nó **gọi `close()` trên nguồn đọc nếu nguồn đó hiện thực `java.io.Closeable`**.
- Nếu nguồn chỉ hiện thực `Readable` mà không phải `Closeable`, Scanner không có phương thức `close()` chung để đóng nguồn đó.
- Gọi `Scanner.close()` lần hai không đóng nguồn thêm lần nữa theo hợp đồng.
- Đọc/tìm kiếm token sau close sẽ ném `IllegalStateException`.
- IOException khi đóng nguồn có thể được ghi vào `ioException()`; không nên nghĩ rằng vì `scanner.close()` trả về bình thường thì chắc chắn mọi thao tác đóng I/O thành công.

Sơ đồ quyền sở hữu:

```text
try-with-resources đóng Scanner
             |
             v
         Scanner.close()
             |
             +-- nguồn implements Closeable?
                    |
                YES | NO
                    | 
                    v
              source.close()        (không có thao tác close nguồn chung)
                    |
             nguồn bọc tiếp có thể
             đóng các luồng bên dưới
```

Ví dụ:

```java
InputStream fileBytes = Files.newInputStream(path);
Scanner scanner = new Scanner(fileBytes, StandardCharsets.UTF_8);
scanner.close();
```

Đây là mảnh mã, với `path` là `Path` hợp lệ, cần import `java.io.*`, `java.nio.file.*`, `java.nio.charset.*`, `java.util.Scanner` và xử lý `IOException` khi mở tệp. Trong ví dụ, Scanner sử dụng một Reader nội bộ để giải mã từ InputStream; khi đóng Scanner, chuỗi wrapper thường đóng cả Reader và InputStream bên dưới. **Vì vậy, đóng Scanner có thể làm cho InputStream ban đầu không dùng được nữa.**

### Quy tắc sở hữu

- **Tự mở tệp trong phương thức hiện tại:** phương thức thường sở hữu tài nguyên và phải đóng khi xong. `try-with-resources` là lựa chọn tự nhiên.
- **Nhận `InputStream` / `Reader` từ đối tượng khác:** hỏi rõ hợp đồng sở hữu; tránh tự ý đóng Scanner khi thành phần gọi còn cần dùng nguồn.
- **Nguồn dùng chung như `System.in`:** thường không nên tự động đóng chỉ vì hoàn tất một lần hỏi người dùng, vì sẽ làm các phần sau của chương trình không còn stdin.
- **Nguồn chỉ là `String` trong bộ nhớ:** đóng Scanner vẫn là thực hành nhất quán về vòng đời, dù không liên quan đến handle tệp/mạng do chương trình giữ.

Đừng tạo nhiều Scanner trên cùng một `InputStream` hoặc `Reader` nếu không kiểm soát được đọc trước/buffering: một Scanner có thể tiêu thụ trước byte/char làm Scanner kia không nhận được dữ liệu như mong đợi.

## 6. Try-with-resources và kiểm tra ioException sau khi đóng

Mẫu cơ bản đọc file với charset tường minh:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.Scanner;

public class ReadFileLines {
    public static void main(String[] args) throws IOException {
        Path path = Path.of("input.txt");

        // Java 9+: có thể dùng một biến effectively final trong try(...).
        Scanner scanner = new Scanner(path, StandardCharsets.UTF_8);

        try (scanner) {
            while (scanner.hasNextLine()) {
                String line = scanner.nextLine();
                System.out.println(line);
            }
        }

        // Chạy sau close: phát hiện cả lỗi đọc và lỗi đóng nguồn.
        IOException failure = scanner.ioException();
        if (failure != null) {
            throw new IOException("Failed to read/close " + path, failure);
        }
    }
}
```

Chạy với JDK 17+:

```bash
javac ReadFileLines.java
java ReadFileLines
```

Khi chạy, tệp `input.txt` phải có sẵn tại **thư mục làm việc hiện tại**. Chương trình in từng dòng đọc được. Vì dữ liệu tùy file, không có một stdout cố định để khẳng định trong tài liệu. Nếu mở file thất bại, constructor có thể ném `IOException` **trước khi** khối `try` bắt đầu; khi đó chưa có Scanner để gọi `ioException()`.

Lý do cố ý khai báo `Scanner scanner` bên ngoài `try`: cần giữ **tham chiếu** để kiểm tra `ioException()` sau khi `try-with-resources` đã thực hiện `close()`. Mặc dù Scanner đã đóng, phương thức `ioException()` vẫn cho biết ngoại lệ I/O được lưu; không gọi `hasNextLine()` nữa.

**Giới hạn quan trọng của mẫu này:** nếu phần xử lý **bên trong** vòng lặp ném ngoại lệ độc lập (ví dụ dữ liệu nghiệp vụ sai), câu lệnh sau khối `try` sẽ không chạy. Ứng dụng cần cơ chế báo cáo lỗi riêng, hoặc kiểm tra `ioException()` trong `finally` nếu nhất thiết phải ghi nhận lỗi I/O ngay cả khi quá trình parse thất bại. Tránh cố tình ném lỗi mới trong `finally` làm che lỗi gốc nếu chưa thiết kế quy tắc ưu tiên ngoại lệ.

### Có phải cứ try-with-resources là tự phát hiện IOException khi đóng?

Không. Với `Scanner`, `close()` có kiểu trả về `void` và **không khai báo `throws IOException`**. Nó có thể giữ `IOException` từ nguồn trong `ioException()` thay vì ném ra ngoài. Do đó:

```java
try (Scanner scanner = new Scanner(source)) {
    consume(scanner);
}
// Việc khối try không ném IOException không chứng minh source.close() thành công.
```

Đây là mảnh mã minh họa: `source` là nguồn có thể đóng, `consume` là hàm xử lý. Nếu ứng dụng cần kiểm tra chắc chắn lỗi đóng, phải giữ tham chiếu để hỏi `ioException()` sau close, hoặc quản lý nguồn/Reader trực tiếp theo cách có hợp đồng truyền lỗi đóng phù hợp.

## 7. Phân biệt lỗi đọc, lỗi parse và EOF

| Biểu hiện | Khả năng | Cách xác minh |
| --- | --- | --- |
| `hasNext() == false` | EOF, không còn token phù hợp, hoặc IOException khi đọc | Kiểm tra `ioException()`; hiểu thêm cấu trúc input |
| `hasNextLine() == false` | Hết dòng hoặc lỗi đọc | Kiểm tra `ioException()` |
| `next()` ném `NoSuchElementException` | Không còn token | Kiểm tra trạng thái parser và `ioException()` |
| `nextInt()` ném `InputMismatchException` | Token không hợp lệ với kiểu/radix/locale | Xử lý dữ liệu sai kiểu; `ioException()` có thể vẫn `null` |
| `nextInt()` ném `NoSuchElementException` | Không còn token để lấy | Không coi ngoại lệ này là chính nó chứng minh IOException |
| `hasNextInt() == false` | Token hiện tại không phải số hoặc không có dữ liệu phù hợp | Có thể dùng `hasNext()` để phân biệt token sai kiểu với thiếu token |
| `ioException() != null` | Nguồn Scanner từng báo IOException khi đọc/đóng | Xử lý nguyên nhân I/O theo ngữ cảnh |

Ví dụ khi nhập số:

```java
if (scanner.hasNextInt()) {
    int number = scanner.nextInt();
    // Xử lý number.
} else if (scanner.hasNext()) {
    String invalidToken = scanner.next();
    // Có token, nhưng token này không parse được thành int.
} else {
    IOException failure = scanner.ioException();
    if (failure != null) {
        // Luồng đọc có IOException.
    } else {
        // Hiện không còn token; thường là EOF hợp lệ.
    }
}
```

Đây là mảnh mã: `scanner` đã được tạo trước, và chương trình dùng các import `java.util.Scanner` / `java.io.IOException`. Nếu nguồn có thể block, mỗi lần `hasNext...` có thể chờ dữ liệu. `Scanner` có buffer và mặc định delimiter là khoảng trắng; cần đặt `useDelimiter`/`useLocale`/`useRadix` theo định dạng thật nếu parser phụ thuộc chúng.

## 8. Xử lý System.in: khi nào không nên close?

Tình huống phổ biến:

```java
Scanner input = new Scanner(System.in, StandardCharsets.UTF_8);
System.out.print("Tên: ");
String name = input.nextLine();
System.out.println("Xin chào " + name);
// Không gọi input.close() nếu nhiều phần của ứng dụng vẫn dùng System.in.
```

Đây là mảnh mã, cần `java.util.Scanner` và `java.nio.charset.StandardCharsets`. Việc không đóng trong đoạn minh họa có mục đích: `System.in` là **nguồn dùng chung**, thường do vòng đời chương trình quản lý. Nếu gọi `input.close()`, chuỗi đóng có thể đóng `System.in`; lần nhập tiếp theo ở thành phần khác có thể không hoạt động.

Tuy nhiên, cũng không có quy tắc tuyệt đối rằng “Scanner trên System.in không bao giờ được đóng”. Ở chương trình CLI độc lập, khi ứng dụng thực sự kết thúc và sở hữu đầu vào, đóng tài nguyên có thể hợp lý. Quyết định dựa trên **ownership và vòng đời**, không dựa trên việc có dùng `try-with-resources` được hay không.

Một số lời khuyên thực dụng:

- Chỉ một thành phần làm chủ Scanner của `System.in` và chuyển dữ liệu/hàm nhập cho các thành phần khác.
- Không tạo rồi đóng Scanner riêng cho từng câu hỏi bàn phím khi còn câu hỏi sau.
- Nếu Scanner tồn tại xuyên suốt phiên CLI, hãy kiểm tra `ioException()` khi kết thúc hoặc khi nhập thất bại.
- Tránh bỏ qua các phương thức có thể **block**, như `hasNext()` hoặc `nextLine()`, khi thiết kế timeout và khả năng hủy ở tầng chương trình.

## 9. Tình huống: Scanner được tạo từ Reader có decoder nghiêm ngặt

Một `Scanner` đọc văn bản có thể nhận dữ liệu từ `InputStreamReader`. Nếu ứng dụng yêu cầu byte UTF-8 phải hoàn toàn hợp lệ, có thể truyền một decoder cấu hình `REPORT`:

```java
CharsetDecoder strict = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

Reader reader = new InputStreamReader(inputStream, strict);
Scanner scanner = new Scanner(reader);
try (scanner) {
    while (scanner.hasNextLine()) {
        String line = scanner.nextLine();
        // Xử lý line.
    }
}
IOException readOrCloseFailure = scanner.ioException();
if (readOrCloseFailure != null) {
    throw readOrCloseFailure;
}
```

Đây là **mảnh mã minh họa**, cần các import `java.io.*`, `java.util.Scanner` và `java.nio.charset.*`; `inputStream` là nguồn byte hợp lệ và phương thức phải xử lý `IOException`.

Nếu `InputStreamReader` gặp byte UTF-8 sai định dạng với cấu hình `REPORT`, nó có thể ném `MalformedInputException` (một `IOException`). Scanner xem lỗi đọc đó như hết input và lưu lại để `ioException()` trả về. Vì thế **chỉ dựa vào `hasNextLine() == false` không đủ** để chứng minh văn bản UTF-8 hợp lệ.

Nếu chọn constructor Scanner với charset mà không truyền decoder cấu hình, đừng mặc định rằng chính sách lỗi ký tự giống cấu hình nghiêm ngặt trên; phải tra hợp đồng API tương ứng. Ngoài ra, `Scanner` không kiểm tra tính hợp lệ của CSV/JSON, số trường, chữ ký hay checksum: đó là trách nhiệm lớp parser/validator nghiệp vụ.

## 10. Nếu xảy ra cả lỗi đọc và lỗi đóng thì sao?

`ioException()` chỉ cung cấp **ngoại lệ I/O gần nhất** Scanner đã ghi nhận; nó không phải lịch sử đầy đủ các lần lỗi. Nếu một nguồn ném `IOException` khi đọc rồi tiếp tục ném `IOException` khác lúc đóng, thông tin lỗi được trả về sau cùng có thể là lỗi close. Không dùng `ioException()` như danh sách đầy đủ các lỗi; nếu cần chẩn đoán cả hai, lưu lại kết quả ngay sau vòng đọc và trước khi đóng.

Ví dụ khung xử lý (minh họa ý tưởng, không phải chương trình độc lập):

```java
Scanner scanner = new Scanner(source);
IOException readFailure;

try {
    while (scanner.hasNextLine()) {
        handle(scanner.nextLine());
    }
    readFailure = scanner.ioException(); // Trước close.
} finally {
    scanner.close();                     // Có thể cập nhật lỗi được lưu.
}

IOException lastFailure = scanner.ioException(); // Sau close.
```

Trong mảnh mã này, `source` là một `Readable` đã biết quyền sở hữu, `handle` là hàm nghiệp vụ, và cần import `java.util.Scanner`/`java.io.IOException`. Nếu `handle` ném exception, biến `readFailure` có thể chưa được gán và câu lệnh sau `finally` không chạy; vì vậy **không dùng nguyên khung này làm mã ứng dụng hoàn chỉnh**. Trong triển khai thật, khởi tạo `readFailure = null` và thiết kế `catch/finally` cùng quy tắc ưu tiên lỗi rõ ràng. Bản chất thông điệp: lỗi có thể đến **trước** hoặc **trong** khi close, còn `ioException()` chỉ nhớ **lần gần nhất**.

Nếu muốn ghi log và báo lỗi chi tiết cho một giao thức nghiêm ngặt, có thể bọc nguồn `Reader`/`InputStream` theo dõi exception trực tiếp, hoặc viết logic đọc ở tầng thấp hơn để phân biệt EOF và failure ngay tại nơi chúng phát sinh.

## 11. Khi nào dùng Scanner, khi nào chuyển sang API khác?

`Scanner` rất tiện cho tách token bằng regex, đọc số và dữ liệu nhập tương tác; nó **không phải lựa chọn duy nhất** khi cần luồng dữ liệu lớn hoặc quản lý lỗi I/O chính xác.

| Nhu cầu | Lựa chọn thường phù hợp |
| --- | --- |
| CLI nhỏ, đọc các số/token và câu trả lời từ người dùng | `Scanner`, với vòng đời `System.in` có chủ |
| Đọc vài dòng tệp và parse token | `Scanner` + try-with-resources + `ioException()` |
| Xử lý tệp văn bản rất lớn theo dòng | `BufferedReader` / `Files.newBufferedReader` hoặc `Files.lines` với đóng nguồn |
| Cần bắt `IOException` ngay tại lần đọc | `BufferedReader.readLine()` hoặc `Reader.read(...)` trực tiếp |
| Giao thức nhị phân có độ dài bản ghi | `InputStream`/`DataInputStream`/channel phù hợp |
| Muốn kiểm tra CSV, JSON hoặc định dạng đặc thù | Parser dành cho định dạng đó, quản lý stream theo hợp đồng của parser |

Ví dụ `BufferedReader`:

```java
try (BufferedReader reader =
        Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        process(line);
    }
}
```

Đây là mảnh mã với `path`, `process` đã được định nghĩa và `IOException` được xử lý. Khác biệt: khi `readLine()` gặp lỗi I/O, nó **có thể ném `IOException` trực tiếp**, nhờ đó logic bắt lỗi tại chỗ tự nhiên hơn. Điều này không có nghĩa `BufferedReader` tự parse số và token như Scanner; hai API đáp ứng các nhiệm vụ khác nhau.

## 12. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Chỉ kiểm tra `hasNext() == false` rồi xem file đọc xong | Lỗi I/O bị ngụy trang thành EOF | Kiểm tra `ioException()` |
| Nghĩ `ioException()` sẽ tự ném lỗi | Lỗi bị bỏ qua | Kiểm tra giá trị khác `null`, báo/throw khi cần |
| Cho rằng `InputMismatchException` là IOException | Phân loại sai lỗi dữ liệu | Bắt/kiểm tra lỗi parse riêng |
| Đóng Scanner trên `System.in` rồi còn nhập tiếp | Đóng nguồn dùng chung | Quản lý ownership và tái sử dụng một Scanner |
| Đóng Scanner rồi gọi `nextLine()` | `IllegalStateException` | Không đọc sau close |
| Cho rằng close không lỗi vì `Scanner.close()` không throw | Bỏ qua IOException khi nguồn đóng | Gọi `ioException()` sau close nếu cần biết |
| Chỉ kiểm tra `ioException()` trước close | Không phát hiện lỗi close | Cân nhắc kiểm tra lần nữa sau close |
| Mở nguồn/tệp lỗi nhưng cố gọi `scanner.ioException()` | Scanner chưa tồn tại | Bắt lỗi tại constructor mở nguồn |
| Tạo nhiều Scanner đọc chung một InputStream | Tranh chấp đọc trước, mất/đảo thứ tự token | Một chủ sở hữu hoặc thiết kế phân phối dữ liệu |
| Cho rằng `ioException() == null` nghĩa file hợp lệ | Bỏ qua thiếu trường, sai định dạng, charset | Xác thực dữ liệu độc lập với lỗi I/O |
| Kết thúc vòng lặp số bằng `hasNextInt() == false` mà không xét token sai kiểu | Token không phải số bị bỏ lại | Kiểm tra `hasNext()` và chính sách dữ liệu đầu vào |
| Dùng `Scanner` trong nhiều thread không đồng bộ | Trạng thái parser không an toàn | Mỗi consumer một nguồn, hoặc đồng bộ rõ ràng |

## 13. Tự kiểm tra kiến thức

1. **`hasNext()` trả `false` có đủ khẳng định EOF bình thường?** Không; Scanner có thể đã nhận `IOException` từ nguồn và coi như hết input.
2. **`ioException()` trả cái gì?** `IOException` gần nhất từ nguồn Scanner ghi nhận, hoặc `null` nếu chưa có.
3. **`ioException()` có ném ngoại lệ đã lưu không?** Không; nó chỉ trả về một đối tượng để ứng dụng xử lý.
4. **Sau khi Scanner.close(), còn gọi `ioException()` được không?** Có; đây là cách phát hiện lỗi close được lưu. Nhưng không được tiếp tục quét token.
5. **Đóng Scanner có luôn đóng nguồn không?** Scanner gọi close nếu nguồn bên dưới thực hiện `Closeable`; với nguồn được bọc, close có thể truyền tiếp xuống các stream.
6. **Vì sao try-with-resources chưa đủ nếu cần phát hiện lỗi đóng nguồn?** `Scanner.close()` có thể giữ IOException bên trong; cần kiểm tra `ioException()` sau đó.
7. **`nextInt()` ném `InputMismatchException` có nghĩa tệp lỗi I/O?** Không; thường nghĩa token hiện tại không parse được thành int.
8. **Mở tệp thất bại ở constructor thì kiểm tra `ioException()` bằng cách nào?** Không thể nếu Scanner chưa được tạo; bắt ngoại lệ trực tiếp của thao tác mở.
9. **Vì sao không tự ý đóng Scanner(System.in)?** Vì đóng scanner có thể đóng nguồn console dùng chung cho các phần khác.
10. **Khi nào ưu tiên BufferedReader?** Khi cần đọc dòng và nhận IOException trực tiếp hơn là phân tích token theo quy tắc Scanner.

## Tham khảo Java 17

- [`Scanner` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Scanner.html).
- [`Readable` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Readable.html).
- [`Closeable` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Closeable.html).
- [`BufferedReader` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedReader.html).
- [`InputStreamReader` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStreamReader.html).

**Ghi nhớ:** `Scanner` có thể biến một `IOException` của nguồn thành kết thúc quét token, nên **`ioException()` là bước kiểm tra quan trọng trước khi kết luận đọc thành công**. `close()` đóng cả nguồn nếu nguồn là `Closeable`; hãy quản lý quyền sở hữu nguồn và kiểm tra lỗi close khi độ tin cậy dữ liệu đòi hỏi.
