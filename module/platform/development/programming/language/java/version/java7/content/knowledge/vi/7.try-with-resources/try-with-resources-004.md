# Nhiều tài nguyên và thứ tự đóng ngược trong try-with-resources (Java 7+)

> **Chủ đề:** Khai báo nhiều đối tượng tài nguyên trong cùng một `try-with-resources`, hiểu thứ tự **khởi tạo từ trái sang phải – đóng từ phải sang trái**, kể cả khi thân `try` lỗi, khởi tạo tài nguyên tiếp theo thất bại hoặc `close()` ném ngoại lệ. Cú pháp xuất hiện ở Java 7 và vẫn được sử dụng trong Java 17+; phần mở rộng dùng biến tài nguyên đã khai báo bên ngoài có từ Java 9. Nội dung tập trung vào hành vi và cách áp dụng còn giá trị trên Java hiện đại.

## 1. Vì sao cần quản lý nhiều tài nguyên cùng lúc?

Một tác vụ thường cần hơn một tài nguyên phải đóng: đọc từ một nguồn và ghi ra đích; mở file rồi làm việc với stream; dùng hai kết nối độc lập; hoặc kết hợp một đối tượng tạm để thu thập dữ liệu với một đối tượng để xuất dữ liệu. Tài nguyên có thể nắm giữ file descriptor, socket, khóa hoặc trạng thái I/O mà chương trình cần giải phóng đúng lúc.

Java cung cấp `try-with-resources` cho những đối tượng triển khai `java.lang.AutoCloseable` (gồm nhiều lớp triển khai `java.io.Closeable`). Khi rời khối `try` theo cách thông thường hoặc do ngoại lệ, Java tự gọi `close()` với các tài nguyên đã khởi tạo thành công và do khối `try` quản lý.

Cấu trúc với hai tài nguyên:

```java
try (
    FirstResource first = acquireFirst();
    SecondResource second = acquireSecond()
) {
    performWork(first, second);
}
```

Đây là **cú pháp minh họa**: các class/method trên được giả định là hợp lệ và tài nguyên phải implement `AutoCloseable`. `FirstResource` và `SecondResource` được khởi tạo **theo đúng thứ tự được liệt kê**; khi kết thúc, `second.close()` được gọi **trước** `first.close()`.

**Đặc điểm quyết định:** vòng đời nhiều tài nguyên theo **ngăn xếp (LIFO — Last In, First Out)**. Đối tượng được quản lý cuối cùng được đóng đầu tiên. Đây là hành vi ngôn ngữ Java, không phụ thuộc việc ứng dụng chạy trên JDK 17, 21 hay nền tảng hệ điều hành nào.

## 2. Cú pháp đúng của danh sách tài nguyên

Từ Java 7, có thể khai báo nhiều *resource declarations*, phân tách bằng dấu chấm phẩy `;`:

```java
try (
    InputStream input = Files.newInputStream(source);
    OutputStream output = Files.newOutputStream(destination)
) {
    // Sử dụng input và output.
}
```

Đây là **snippet trong method** có `Path source`, `Path destination` và các import từ `java.io`/`java.nio.file`. Các method `Files.newInputStream`, `Files.newOutputStream` thuộc NIO.2 từ Java 7 và vẫn đang được sử dụng.

### 2.1. Luật cơ bản

- **Phân tách tài nguyên bằng `;`**, không dùng dấu phẩy `,`. Một dấu `;` cuối danh sách cũng được phép, nhưng không bắt buộc.
- Từng biểu thức tài nguyên phải có kiểu triển khai `AutoCloseable` hoặc subtype thích hợp. Với tài nguyên được khai báo trong header, biến của nó được xem như **final**: không thể gán lại trong thân `try`.
- Những biểu thức khởi tạo được **đánh giá tuần tự từ trái sang phải**. Nếu khởi tạo thất bại, Java không tiếp tục khởi tạo các tài nguyên phía sau.
- Các tài nguyên khởi tạo thành công được **đóng theo thứ tự ngược**.
- Mỗi tài nguyên trong header có thể được truy cập trong thân `try` theo phạm vi của khai báo; tài nguyên khai báo trước có thể được tham chiếu khi khởi tạo tài nguyên sau nếu cần.
- `catch` và `finally` đi kèm có thể dùng để xử lý kết quả, nhưng việc tự động đóng tài nguyên của khối `try` hoàn tất **trước khi** chạy các nhánh này.

### 2.2. `AutoCloseable` và `Closeable`

`AutoCloseable` có method `void close() throws Exception`. `Closeable` (thuộc `java.io`) kế thừa `AutoCloseable` nhưng method `close()` khai báo `throws IOException`. Class cụ thể có thể override `close()` với một loại checked exception hẹp hơn hoặc không khai báo checked exception nào.

Vì vậy, khi dùng nhiều tài nguyên, compiler phải xét **những checked exception có thể xảy ra khi mở, làm việc và đóng từng tài nguyên**. Nếu một tài nguyên có `close() throws Exception` và lỗi này không được bắt, method có thể phải khai báo `throws Exception`; với `Closeable` thường là `IOException`. Không phải cứ có nhiều tài nguyên là mọi method đều cần `throws Exception` — điều đó phụ thuộc kiểu tĩnh và hợp đồng `close()` của từng resource.

## 3. Thứ tự chính xác: tạo A → tạo B → tạo C; đóng C → đóng B → đóng A

Xem chương trình đầy đủ sau. Nó dùng tài nguyên tự định nghĩa để in sự kiện, giúp thấy thứ tự mà không phụ thuộc filesystem hay mạng.

Lưu thành `ReverseCloseDemo.java`:

```java
public class ReverseCloseDemo {
    static final class Tracked implements AutoCloseable {
        private final String name;

        Tracked(String name) {
            this.name = name;
            System.out.println("open " + name);
        }

        @Override
        public void close() {
            System.out.println("close " + name);
        }
    }

    public static void main(String[] args) {
        try (
            Tracked first = new Tracked("A");
            Tracked second = new Tracked("B");
            Tracked third = new Tracked("C")
        ) {
            System.out.println("body");
        }
    }
}
```

Biên dịch và chạy trên JDK 17+:

```bash
javac -encoding UTF-8 --release 17 ReverseCloseDemo.java
java ReverseCloseDemo
```

Stdout chính xác:

```text
open A
open B
open C
body
close C
close B
close A
```

**Cách đọc dòng thời gian:**

1. Java khởi tạo `first`, gọi constructor `Tracked("A")` → in `open A`.
2. Khởi tạo `second` → `open B`.
3. Khởi tạo `third` → `open C`.
4. Khi cả ba đã sẵn sàng, thân `try` chạy → `body`.
5. Thoát thân `try`, Java đóng `third` trước (`close C`), rồi `second` (`close B`), cuối cùng `first` (`close A`).

Không cần gọi `first.close()`, `second.close()` hay `third.close()` thủ công trong thân `try`. Việc đóng ngược được bảo đảm bởi quy tắc của `try-with-resources`, không phải do Java “tình cờ” lặp ngược một mảng.

Một cách hình dung tương đương là các `try-with-resources` lồng nhau: tài nguyên ở lớp trong cùng kết thúc trước lớp ngoài. Tuy nhiên, hãy dùng cú pháp danh sách khi các tài nguyên thuộc cùng một thao tác và phạm vi sống giống nhau — nó ngắn gọn và thể hiện rõ quyền sở hữu tài nguyên.

## 4. Nếu khởi tạo tài nguyên thứ hai thất bại thì sao?

Một trong những ưu điểm quan trọng nhất là **an toàn khi khởi tạo từng phần**. Giả sử A mở thành công nhưng biểu thức tạo B ném exception. Trước khi exception được truyền ra ngoài:

- A **đã được khởi tạo thành công**, nên Java sẽ đóng A.
- B **không được tạo thành công**, nên không có đối tượng B hoàn tất đăng ký để Java tự gọi `close()`.
- C **chưa được khởi tạo**, vì quá trình đánh giá dừng ở B.
- Thân `try` **không được thực thi**.

Lưu thành `PartialInitializationDemo.java`:

```java
public class PartialInitializationDemo {
    static final class Tracked implements AutoCloseable {
        private final String name;

        Tracked(String name) {
            this.name = name;
            System.out.println("open=" + name);
        }

        @Override
        public void close() {
            System.out.println("close=" + name);
        }
    }

    static Tracked create(String name, boolean fail) {
        System.out.println("init=" + name);

        if (fail) {
            throw new IllegalArgumentException("cannot open " + name);
        }
        return new Tracked(name);
    }

    public static void main(String[] args) {
        try (
            Tracked first = create("A", false);
            Tracked second = create("B", true);
            Tracked third = create("C", false)
        ) {
            System.out.println("body");
        } catch (IllegalArgumentException error) {
            System.out.println("caught=" + error.getMessage());
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 PartialInitializationDemo.java
java PartialInitializationDemo
```

```text
init=A
open=A
init=B
close=A
caught=cannot open B
```

**Điểm cần chú ý:** `init=C` không xuất hiện, thân `try` không chạy, nhưng `close=A` vẫn xảy ra. Đây là lý do nên **khai báo việc mở nhiều tài nguyên trực tiếp trong header** thay vì tự mở tất cả bên ngoài rồi mới đặt vào một `try`.

### 4.1. Nếu constructor tạo ra tài nguyên rồi ném exception giữa chừng?

`try-with-resources` chỉ tự đóng **những đối tượng đã được khởi tạo thành công và được đăng ký trong danh sách tài nguyên**. Nếu factory/constructor đã lấy được một phần tài nguyên nội bộ rồi ném exception **trước khi trả về đối tượng**, chính factory/constructor phải chịu trách nhiệm giải phóng phần nội bộ đó. Header `try` không thể tự nhận quyền sở hữu một object chưa được trả về hoặc chưa được gán thành công.

Quy tắc thực tế: factory mở nhiều thành phần phải có chiến lược cleanup nếu mở dang dở; khi có thể, bố trí các thành phần là những resource được khai báo tuần tự trong header để tận dụng cơ chế đóng khi init sau thất bại.

## 5. Đóng tài nguyên cả khi `return`, `break` hoặc ném exception

Không chỉ kết thúc bình thường: nếu thân `try` thực hiện `return` hoặc ném exception, những tài nguyên thuộc quyền quản lý vẫn được đóng theo thứ tự ngược **trước khi điều khiển được chuyển ra ngoài**.

Lưu thành `EarlyReturnDemo.java`:

```java
public class EarlyReturnDemo {
    static final class Tracked implements AutoCloseable {
        private final String name;

        Tracked(String name) {
            this.name = name;
            System.out.println("open " + name);
        }

        @Override
        public void close() {
            System.out.println("close " + name);
        }
    }

    static String getValue() {
        try (
            Tracked first = new Tracked("A");
            Tracked second = new Tracked("B")
        ) {
            System.out.println("inside");
            return "READY";
        }
    }

    public static void main(String[] args) {
        System.out.println("result=" + getValue());
    }
}
```

```bash
javac -encoding UTF-8 --release 17 EarlyReturnDemo.java
java EarlyReturnDemo
```

```text
open A
open B
inside
close B
close A
result=READY
```

Mặc dù `getValue()` gặp `return "READY"` trong thân, thứ tự vẫn là `close B`, `close A` rồi caller mới in `result=READY`. Điều tương tự áp dụng cho các lối thoát có kiểm soát khác như `break` và `continue` trong cấu trúc vòng lặp.

**Ngoại lệ quan trọng:** nếu một `close()` ném exception trong quá trình hoàn tất một `return`, việc trả về dự kiến có thể bị thay bằng exception đó. Không được hiểu `return` là luôn thắng bất kể lỗi đóng tài nguyên. Cũng không nên suy rộng bảo đảm đóng tài nguyên cho tình huống tiến trình bị cưỡng bức kết thúc, máy tắt hoặc JVM dừng đột ngột; `try-with-resources` quản lý các đường đi thực thi bình thường của ngôn ngữ.

## 6. Nếu thân try và nhiều lệnh close đều ném exception?

Đây là phần quan trọng nhất khi làm việc với nhiều resource. Java cần giữ được **lỗi chính (primary exception)** mà không làm mất các lỗi xảy ra khi dọn dẹp. Cơ chế **suppressed exceptions** giải quyết bài toán này.

### 6.1. Khi thân try ném exception

Giả sử:

1. Mở A rồi mở B.
2. Thân `try` ném `IllegalStateException("body-failed")`.
3. Java gọi `B.close()` trước và `B.close()` ném `IOException("close-B")`.
4. Java **vẫn tiếp tục** gọi `A.close()`; `A.close()` cũng ném `IOException("close-A")`.
5. Exception từ thân `try` vẫn là **primary**; hai lỗi đóng B và A được gắn làm **suppressed exceptions**.

Đọc suppressed bằng `Throwable.getSuppressed()`. Thứ tự đóng là B rồi A, nên các lỗi từ chúng thường được bổ sung theo thứ tự **close-B, close-A**.

### 6.2. Khi thân try chạy thành công nhưng close ném exception

Giả sử thân `try` không ném gì, nhưng B.close và A.close đều ném:

1. B được đóng trước và lỗi `close-B` trở thành **primary**.
2. Java vẫn đóng A; lỗi `close-A` được gắn vào `close-B` dưới dạng **suppressed**.
3. Caller nhận lỗi từ B.close, không phải kết quả thành công của toàn bộ lệnh `try`.

Vì vậy không thể cho rằng “code trong body chạy xong thì cả thao tác đã thành công” nếu ý nghĩa hoàn tất yêu cầu tài nguyên đóng/flush thành công.

## 7. Ví dụ chạy được: primary và suppressed theo thứ tự đóng ngược

Lưu thành `SuppressedOrderDemo.java`:

```java
import java.io.IOException;

public class SuppressedOrderDemo {
    static final class FailingClose implements AutoCloseable {
        private final String name;

        FailingClose(String name) {
            this.name = name;
            System.out.println("open " + name);
        }

        @Override
        public void close() throws IOException {
            System.out.println("close " + name);
            throw new IOException("close-" + name);
        }
    }

    static void printFailure(Exception error) {
        System.out.println("primary=" + error.getMessage());
        for (Throwable suppressed : error.getSuppressed()) {
            System.out.println("suppressed=" + suppressed.getMessage());
        }
    }

    public static void main(String[] args) {
        try (
            FailingClose a = new FailingClose("A");
            FailingClose b = new FailingClose("B")
        ) {
            System.out.println("body");
            throw new IllegalStateException("body-failed");
        } catch (Exception error) {
            printFailure(error);
        }

        try (
            FailingClose a = new FailingClose("A");
            FailingClose b = new FailingClose("B")
        ) {
            System.out.println("ok");
        } catch (Exception error) {
            printFailure(error);
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 SuppressedOrderDemo.java
java SuppressedOrderDemo
```

```text
open A
open B
body
close B
close A
primary=body-failed
suppressed=close-B
suppressed=close-A
open A
open B
ok
close B
close A
primary=close-B
suppressed=close-A
```

**Vì sao kết quả như vậy?**

- Trường hợp đầu: `IllegalStateException` từ body là primary. B.close và A.close gây ra hai `IOException` được thêm vào danh sách suppressed. Cả hai close vẫn được thử gọi, dù B.close đã thất bại.
- Trường hợp sau: body không ném exception, nên lỗi đầu tiên trong quá trình đóng (B.close) làm primary; lỗi còn lại A.close là suppressed.
- `getMessage()` dùng ở đây vì chúng ta tự tạo chuỗi cố định. Trong ứng dụng thật, dùng thông tin exception type, stack trace và nguyên nhân, không giả định message luôn cố định.

**Đặc biệt với nhiều tài nguyên:** cơ chế này ngăn lỗi đóng cuối cùng ghi đè hoàn toàn lỗi gốc. Tuy nhiên, “suppressed” **không có nghĩa là vô hại hoặc có thể bỏ qua**: lỗi đóng file/flush/commit có thể quan trọng. Khi chẩn đoán, phải xem cả primary exception và danh sách suppressed. Những hàm log chuẩn in stack trace của `Throwable` thường hiển thị mục suppressed; khi chuyển exception qua tầng khác, đừng tự cắt bỏ dữ liệu này.

### 7.1. Nếu init B lỗi và A.close cũng lỗi?

Cùng nguyên lý được áp dụng cho lỗi trong **biểu thức khởi tạo**. Nếu khởi tạo B ném exception sau khi A đã được khởi tạo thành công, Java đóng A. Nếu A.close cũng ném lỗi, exception từ **khởi tạo B** thường là primary, còn lỗi đóng A là suppressed.

Đây là sự mở rộng trực tiếp của tình huống `PartialInitializationDemo` (ở đó A.close không ném lỗi). Không cần viết `finally` thủ công để bảo toàn hai lỗi.

### 7.2. Đừng chủ động nuốt hoặc thay toàn bộ ngoại lệ

Mã xử lý kém:

```java
try (MyResource a = acquireA(); MyResource b = acquireB()) {
    use(a, b);
} catch (Exception error) {
    System.out.println("Failed");
    // Tự nuốt hoàn toàn lỗi: caller có thể nghĩ tác vụ đã thành công.
}
```

Đây là **pseudocode Java**, `MyResource` và các helper chỉ là tên minh họa. Nếu nghiệp vụ cần báo lỗi, nên ném lại hoặc chuyển sang exception ở tầng phù hợp, giữ `cause`. Không gọi `getSuppressed()` rồi “đánh dấu đã xử lý” nếu chương trình vẫn cần thông báo lỗi đóng tài nguyên cho vận hành.

## 8. Thứ tự `close` so với `catch` và `finally`

`catch` và `finally` của cùng một câu lệnh `try-with-resources` chạy **sau khi Java đã cố gắng đóng các resource được quản lý**.

Sơ đồ đường đi:

```text
Khởi tạo A → Khởi tạo B → Chạy body
                              ↓
                       close B → close A
                              ↓
                  catch phù hợp (nếu có lỗi)
                              ↓
                    finally (nếu có)
                              ↓
                     Lệnh sau try
```

Nếu body có exception, việc đóng diễn ra trước khi bắt lỗi ở catch. Nếu chỉ close có lỗi, catch vẫn có thể nhận exception đó. Nếu catch tạo exception mới, finally vẫn chạy theo quy tắc xử lý ngoại lệ Java; finally cũng có thể phát sinh lỗi riêng, nên không đặt các thao tác dọn dẹp dễ lỗi vào finally một cách tùy tiện khi đã có `AutoCloseable`.

Snippet giúp nhận ra thứ tự:

```java
try (Tracked a = new Tracked("A"); Tracked b = new Tracked("B")) {
    throw new IllegalStateException("failed");
} catch (IllegalStateException error) {
    System.out.println("catch");
} finally {
    System.out.println("finally");
}
```

Đây là snippet dùng lại class `Tracked` có `close()` không ném ở phần 3. Kết quả về thứ tự sau khi đã mở cả hai là: `close B`, `close A`, `catch`, `finally`. Thân catch không bắt đầu khi hai tài nguyên chưa được đóng xong.

**Lưu ý:** một `catch (IOException e)` hoặc `catch (Exception e)` cần được chọn dựa trên **những exception thực sự có thể được ném bởi body, khởi tạo, đóng resource**, không mặc định tất cả chúng chỉ xuất phát từ body.

## 9. Ví dụ thực tế: đọc và ghi file bằng hai resource

Một tác vụ copy file điển hình cần một `InputStream` để đọc từ nguồn và một `OutputStream` để ghi ra đích. Khai báo input trước output giúp nếu mở output thất bại, input đã mở được đóng lại; khi kết thúc, output đóng trước input.

Lưu thành `TwoStreamCopyDemo.java`:

```java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class TwoStreamCopyDemo {
    static long copy(Path source, Path destination) throws IOException {
        try (
            InputStream input = Files.newInputStream(source);
            OutputStream output = Files.newOutputStream(destination)
        ) {
            byte[] buffer = new byte[8192];
            long bytesCopied = 0;
            int length;

            while ((length = input.read(buffer)) != -1) {
                output.write(buffer, 0, length);
                bytesCopied += length;
            }
            return bytesCopied;
        }
    }

    public static void main(String[] args) throws IOException {
        Path source = Files.createTempFile("copy-source-", ".txt");
        Path destination = Files.createTempFile("copy-target-", ".txt");

        try {
            Files.writeString(source, "Java 7", StandardCharsets.UTF_8);

            System.out.println("bytes=" + copy(source, destination));
            System.out.println(
                "text=" + Files.readString(destination, StandardCharsets.UTF_8)
            );
        } finally {
            Files.deleteIfExists(destination);
            Files.deleteIfExists(source);
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 TwoStreamCopyDemo.java
java TwoStreamCopyDemo
```

```text
bytes=6
text=Java 7
```

**Chú giải:**

- `Files.newInputStream` và `Files.newOutputStream` là API NIO.2 từ **Java 7**. `InputStream` và `OutputStream` đều thuộc `Closeable` nên tương thích `try-with-resources`.
- Input được mở **trước** output. Nếu khởi tạo output ném exception, input đã mở sẽ được tự động đóng.
- Lệnh `return bytesCopied` trong thân `try` không bỏ qua cleanup: output đóng rồi input đóng trước khi caller nhận giá trị.
- `Files.writeString` và `Files.readString` được bổ sung từ **Java 11**; chúng dùng ở phần chuẩn bị/kiểm tra dữ liệu minh họa trên JDK 17+. Cơ chế quản lý resource vẫn là tính năng Java 7.
- Ví dụ dùng hai tệp tạm được tạo riêng và cố gắng xóa trong `finally`. Nếu không có quyền tạo file tạm, chương trình có thể gặp lỗi I/O thực tế; dòng stdout trên là kết quả mong đợi trong môi trường cho phép thao tác file.
- Trong ứng dụng thực tế, **không copy nguồn vào chính đích** mà không có biện pháp bảo vệ: mở output có thể làm thay đổi hoặc cắt ngắn dữ liệu tệp đích. Quy tắc đóng đúng không tự giải quyết logic bảo toàn dữ liệu.
- Có `Files.copy(...)` nếu mục tiêu chỉ là copy file mà không cần xử lý thủ công byte stream. Ví dụ ở đây dùng hai resource để minh họa rõ thứ tự đóng.

## 10. Tài nguyên phụ thuộc nhau: đóng ngược có ý nghĩa gì?

Một tài nguyên có thể **bao bọc** tài nguyên khác, ví dụ `BufferedReader` bao quanh `Reader` hoặc `BufferedOutputStream` bao quanh `OutputStream`. Lúc đó, đóng tầng ngoài trước thường cần thiết để **flush buffer và đóng/tất toán trạng thái tầng trong** trước khi nguồn cuối cùng được giải phóng.

Ví dụ:

```java
try (
    InputStream raw = Files.newInputStream(path);
    BufferedInputStream buffered = new BufferedInputStream(raw)
) {
    int value = buffered.read();
    // ...
}
```

Đây là **snippet trong method** với `Path path` và các import phù hợp. Java sẽ đóng `buffered` trước, rồi `raw`. Nhưng `BufferedInputStream.close()` có thể đã đóng `raw` mà nó bao bọc; việc đóng `raw` lần nữa là **đóng trùng**. Nhiều implementation JDK chịu được việc gọi close lặp lại, nhưng **không được suy ra mọi AutoCloseable đều idempotent**.

Khi tầng ngoài **sở hữu** và có trách nhiệm đóng tầng trong, cách gọn hơn thường là chỉ đăng ký **resource ngoài cùng**:

```java
try (
    BufferedInputStream buffered =
        new BufferedInputStream(Files.newInputStream(path))
) {
    int value = buffered.read();
    // ...
}
```

`BufferedInputStream` sở hữu stream được truyền vào, và đóng wrapper sẽ đóng stream bên dưới theo hợp đồng của class này. Với các wrapper khác, luôn kiểm tra tài liệu ownership: có wrapper **không** nên đóng nguồn ở một tầng nhất định, hoặc cần flush/commit trước khi close.

**Quy tắc quan trọng:** “đóng ngược” là bảo đảm về thứ tự gọi `close()`, **không phải** giấy phép đóng nhiều lần một đối tượng mà không có hậu quả. Hãy xác định chính xác ai sở hữu từng resource và tài nguyên nào cần đăng ký trong header.

## 11. Java 9+: có thể dùng biến tài nguyên đã khai báo trước

Cú pháp ban đầu của Java 7 khai báo resource trực tiếp trong header. Từ **Java 9**, nếu biến tài nguyên đã tồn tại và là `final` hoặc **effectively final**, ta có thể đưa biến đó vào header mà không khai báo lại:

```java
BufferedReader reader = Files.newBufferedReader(path);
try (reader) {
    System.out.println(reader.readLine());
}
```

Đây là snippet với import `BufferedReader`, `Files`, `Path`, và method phù hợp. Biến `reader` không được gán lại sau khởi tạo nên đáp ứng yêu cầu *effectively final*. Cú pháp `try (reader)` **không biên dịch với `--release 8`**, nhưng biên dịch được trên Java 9+.

### 11.1. Dùng nhiều biến đã tồn tại

```java
Tracked first = new Tracked("A");
Tracked second = new Tracked("B");

try (first; second) {
    System.out.println("body");
}
```

Đây là snippet dùng `Tracked` ở phần 3; trên Java 17+ cũng đóng `second` trước `first`. Tuy nhiên, nó có một khác biệt **về ranh giới an toàn khi khởi tạo** so với khai báo tài nguyên ngay trong header.

### 11.2. Bẫy khi mở resource bên ngoài header

Xét:

```java
Tracked first = openFirst();    // Mở A thành công.
Tracked second = openSecond();  // Nếu ném exception, chưa vào try!

try (first; second) {
    performWork(first, second);
}
```

Đây là mã minh họa với helper giả định. Nếu `openSecond()` ném exception, chương trình **chưa bước vào** `try (first; second)`, nên cơ chế đóng tài nguyên của khối này **không tự đóng `first`**. Đây là khác biệt rất dễ bị bỏ sót khi refactor từ khai báo trong header ra ngoài.

Để bảo đảm A được đóng ngay cả khi mở B thất bại, ưu tiên:

```java
try (
    Tracked first = openFirst();
    Tracked second = openSecond()
) {
    performWork(first, second);
}
```

Cú pháp ở đoạn sau tồn tại từ Java 7 và khắc phục chính xác lỗ hổng này. Chỉ dùng dạng biến bên ngoài khi vòng đời biến thật sự cần như vậy và bảo đảm cả đoạn khởi tạo trước `try` có cleanup phù hợp.

## 12. Các lỗi thường gặp khi dùng nhiều tài nguyên

| Sai lầm | Tác động | Cách sửa |
| --- | --- | --- |
| Tưởng tài nguyên đóng theo thứ tự khai báo A → B → C | Thiết kế sai phụ thuộc hoặc debug sai thứ tự | Nhớ **khởi tạo xuôi, đóng ngược** |
| Mở A và B bên ngoài, chỉ bắt đầu `try (a; b)` sau khi cả hai sẵn sàng | Nếu mở B lỗi, A có thể rò rỉ | Đưa các thao tác mở vào header `try` |
| Gọi `close()` thủ công trong thân try rồi để Java tự đóng lại | Có thể đóng trùng và gây lỗi trạng thái | Để một nơi chịu trách nhiệm sở hữu/đóng |
| Nghĩ B.close ném exception thì Java bỏ qua A.close | Có thể hiểu sai cleanup và xử lý lỗi | Java vẫn cố đóng các resource còn lại theo thứ tự ngược |
| Bỏ qua `getSuppressed()` khi body và close cùng lỗi | Mất thông tin lỗi đóng/flush | Xem cả primary và suppressed exceptions |
| Coi việc `return` trong body đồng nghĩa bỏ qua đóng tài nguyên | Đánh giá sai vòng đời | Đóng xảy ra trước khi trả về; close có thể ném |
| Dùng `catch (Exception e)` và nuốt toàn bộ lỗi | Che nguyên nhân, caller khó chẩn đoán | Xử lý hoặc truyền lỗi theo hợp đồng, giữ cause |
| Đăng ký cả wrapper và nguồn mà wrapper đã đóng | Đóng trùng, phụ thuộc tính idempotent | Xác định ownership và chỉ đăng ký tài nguyên cần thiết |
| Cho rằng kiểu `AutoCloseable` nào cũng chỉ ném `IOException` | Sai hợp đồng checked exception | Kiểm tra khai báo `close()` của kiểu tĩnh |
| Dùng cú pháp `try (existingVariable)` khi biên dịch Java 8 | Lỗi cú pháp vì tính năng từ Java 9 | Dùng resource declaration trong header |
| Dùng dấu phẩy thay dấu chấm phẩy giữa resource declarations | Lỗi cú pháp | Dùng `;` |
| Quên kiểm tra lỗi đóng trước khi xác nhận thành công toàn bộ thao tác | Có thể báo thành công dù flush/close thất bại | Để exception từ close được xử lý đúng |

### 12.1. Không gộp lỗi chính và lỗi đóng thành một thông điệp mất thông tin

Khi ghi log ở production, in hoặc lưu cấu trúc exception đúng cách thay vì chỉ `error.getMessage()`. Ví dụ có thể ghi cả loại exception, cause chain và suppressed; đừng đưa dữ liệu nhạy cảm vào log. Nếu chuyển exception sang lỗi nghiệp vụ mới, hãy dùng constructor nhận `cause` khi có thể. `Throwable.addSuppressed(...)`/`getSuppressed()` là API Java 7 vẫn hợp lệ; không cần tự triển khai cơ chế suppression thay cho try-with-resources.

### 12.2. Kiểu của resource ảnh hưởng đến lệnh đóng được gọi

Nếu biến có kiểu tĩnh `AutoCloseable`, compiler thấy `close() throws Exception` của interface. Nếu dùng `Closeable` hoặc class có override hẹp hơn, compiler có thể tính một tập checked exception cụ thể hơn. Thứ tự đóng **không đổi** chỉ vì kiểu tĩnh, nhưng yêu cầu `catch`/`throws` có thể thay đổi.

### 12.3. “Đóng” không nhất thiết nghĩa là giao dịch thành công

Với những tài nguyên có transaction/commit semantics riêng, chỉ gọi `close()` chưa chắc tương đương `commit`. Một kết nối database có thể cần commit/rollback rõ ràng theo hợp đồng; một output stream có thể cần flush và xác nhận lỗi ghi. Hãy dùng try-with-resources để quản lý lifetime nhưng vẫn thiết kế nghiệp vụ đúng với API đang dùng.

## 13. Bài tập thực hành có đáp án

**Bài 1 — Dự đoán thứ tự.**  
Trong `try (Resource a = ...; Resource b = ...; Resource c = ...) { body(); }`, nếu mọi thứ chạy thành công, thứ tự mở và đóng là gì?

**Đáp án:** Khởi tạo A, B, C; chạy body; đóng C, B, A. Không phải A, B, C.

**Bài 2 — Khởi tạo thất bại.**  
Đã mở A, biểu thức tạo B ném exception, C đứng sau B. Java làm gì?

**Đáp án:** Không khởi tạo C, không chạy body, nhưng cố đóng A trước khi truyền exception ra ngoài. B chưa được khởi tạo thành công nên không được đăng ký để tự đóng.

**Bài 3 — Return sớm.**  
Một method `return` ngay trong thân `try` quản lý A, B. Caller có thấy kết quả trước khi đóng B, A không?

**Đáp án:** Không. `close(B)` rồi `close(A)` diễn ra trước khi caller nhận kết quả, nếu cả hai close thành công. Nếu close ném exception, return có thể bị thay bằng lỗi.

**Bài 4 — Body và close đều lỗi.**  
Body ném `IllegalStateException`; B.close và A.close đều ném `IOException`. Exception nào là primary, thứ tự suppressed thế nào?

**Đáp án:** Body exception là primary. Suppressed lần lượt là lỗi từ B.close rồi A.close.

**Bài 5 — Chỉ close lỗi.**  
Body hoàn thành bình thường; B.close và A.close đều lỗi. Exception nào caller nhận?

**Đáp án:** Lỗi đầu tiên khi đóng, tức B.close, là primary; A.close nằm trong suppressed của B.

**Bài 6 — Dùng wrapper.**  
`BufferedInputStream buffered` bao bọc `InputStream raw`; tại sao thường không cần đăng ký cả raw và buffered trong header?

**Đáp án:** Đóng buffered theo hợp đồng đã đóng nguồn raw mà nó bao bọc. Đăng ký cả hai có thể khiến raw bị đóng lần hai. Cần xác định ai sở hữu nguồn và tính an toàn khi close nhiều lần.

**Bài 7 — Cú pháp Java 9.**  
Viết `Tracked a = ...; Tracked b = ...; try (a; b) { ... }` có được không trên JDK 17? Có bảo vệ A nếu câu lệnh tạo B ném lỗi trước khi vào try không?

**Đáp án:** Có, nếu a và b final/effectively final. Nhưng không: nếu tạo B ném lỗi trước lệnh try, A chưa thuộc phạm vi cleanup tự động của try.

**Bài 8 — Kiểm tra biên dịch.**  
Thử thay dấu `;` trong danh sách resource bằng dấu `,`, và thử gán lại một biến resource đã khai báo trong header. Giải thích thông báo compiler.

**Đáp án:** Dấu `,` không phải ký hiệu phân tách resource declarations; resource variable không được gán lại trong thân vì được quản lý như biến final.

**Bài 9 — Lập trình.**  
Viết chương trình có ba `AutoCloseable` tùy chỉnh, in thời điểm mở/đóng; thay đổi một resource để ném lỗi ở `close()`. Chạy lần lượt các kịch bản: body thành công; body ném lỗi; resource thứ hai khởi tạo thất bại. In `getSuppressed()`.

**Bài 10 — Ứng dụng thực tế.**  
Mở `InputStream` và `OutputStream` trong một `try`, sao chép dữ liệu; mô phỏng lỗi mở output để xác nhận input vẫn đóng. Sau đó xét khả năng đóng trùng khi thay input bằng một wrapper có sở hữu luồng bên trong.

## 14. Tổng kết nhanh

- Nhiều tài nguyên được ngăn bằng `;` trong header `try-with-resources`.
- **Khởi tạo theo thứ tự khai báo từ trái sang phải.**
- **Đóng theo thứ tự ngược từ phải sang trái.**
- Nếu một resource khởi tạo thất bại, các resource trước đó đã mở thành công vẫn được đóng; các resource sau đó không được mở.
- Đóng xảy ra trước khi `catch`, `finally` của cùng statement chạy và trước khi caller nhận giá trị `return`.
- Nếu body có lỗi, lỗi từ `close` thường được lưu ở `getSuppressed()`. Nếu body không lỗi, lỗi close đầu tiên theo thứ tự ngược có thể là primary; các lỗi close sau đó bị suppress.
- Từ Java 9 có thể đưa biến final/effectively final đã khai báo trước vào `try (...)`, nhưng phải tự bảo vệ đường lỗi **trong quá trình khởi tạo bên ngoài header**.
- Xác định **ownership** khi resource bao bọc resource khác; tránh đóng trùng hoặc nhầm `close` với `commit`.

## 15. Tài liệu chuẩn

- [Java Language Specification 17 — `14.20.3: try-with-resources](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3): khởi tạo, đóng ngược, completion và suppressed exceptions.
- [Java SE 17 — AutoCloseable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): hợp đồng `close()` và lưu ý về idempotence.
- [Java SE 17 — Closeable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Closeable.html): tài nguyên I/O có `close() throws IOException`.
- [Java SE 17 — Throwable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): `getSuppressed()`, `addSuppressed()` và nguyên nhân lỗi.
- [Java SE 17 — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): các API mở luồng với `Path`.

**Ghi nhớ quan trọng nhất:** Đọc `try (A a = ...; B b = ...; C c = ...)` như một ngăn xếp quản lý vòng đời: **mở A → B → C, đóng C → B → A**. Trường hợp lỗi không đảo ngược quy tắc này; Java tiếp tục cố đóng các resource đã khởi tạo và giữ thông tin lỗi bằng cơ chế primary/suppressed. Đây là lý do try-with-resources nhiều tài nguyên vẫn là lựa chọn chuẩn trong Java hiện đại.
