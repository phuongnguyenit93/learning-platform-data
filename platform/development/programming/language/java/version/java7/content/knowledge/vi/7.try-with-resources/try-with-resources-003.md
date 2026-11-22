# Điều kiện tài nguyên triển khai `AutoCloseable` để dùng trong `try-with-resources` (Java)

## 1. Mục tiêu: giải phóng tài nguyên đúng lúc, kể cả khi có lỗi

Trong Java, một số đối tượng đại diện cho **tài nguyên phải được đóng** sau khi dùng: luồng đọc/ghi tệp, reader/writer, socket, kết nối cơ sở dữ liệu, statement/result set và một số tài nguyên do thư viện hoặc ứng dụng tự định nghĩa. Nếu không đóng đúng lúc, chương trình có thể giữ file descriptor, kết nối hoặc bộ nhớ native lâu hơn dự kiến.

Từ **Java 7**, cú pháp **try-with-resources** giúp xác định một vùng sử dụng tài nguyên và yêu cầu Java tự gọi phương thức `close()` khi rời vùng đó:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

// Đặt trong một phương thức có khai báo throws IOException.
try (BufferedReader reader = Files.newBufferedReader(Path.of("data.txt"))) {
    System.out.println(reader.readLine());
}
```

Đây là đoạn minh họa bên trong phương thức, không phải tệp Java chạy độc lập. Đường dẫn `data.txt` phải trỏ đến tệp thực tế. `Files.newBufferedReader` trả về `BufferedReader`, một tài nguyên có thể đóng; Java tự gọi `reader.close()` khi khối `try` kết thúc, dù kết thúc bình thường hay xảy ra ngoại lệ.

**Điều kiện cốt lõi:** Kiểu tài nguyên được đặt trong phần khai báo tài nguyên của `try (...)` phải là kiểu **triển khai giao diện `java.lang.AutoCloseable` hoặc kiểu con của nó**. Đây là điều kiện ở thời điểm biên dịch, không chỉ là đối tượng “có một phương thức tên `close`”.

## 2. `AutoCloseable` là gì?

`AutoCloseable` là một giao diện trong `java.lang`, nên không cần `import` riêng. Hợp đồng phương thức chính có dạng:

```java
public interface AutoCloseable {
    void close() throws Exception;
}
```

Dòng trên minh họa chữ ký quan trọng của giao diện, không phải mã người học cần tự khai báo lại. Trong một lớp triển khai, `close()` phải là phương thức **`public`**, trả về `void` và không có tham số.

Một đối tượng được chấp nhận làm tài nguyên trong `try-with-resources` khi **kiểu tĩnh** của khai báo hoặc biểu thức tài nguyên tương thích với `AutoCloseable`. Các trường hợp hợp lệ:

- Lớp khai báo `implements AutoCloseable` trực tiếp.
- Lớp triển khai một giao diện con của `AutoCloseable`, ví dụ `java.io.Closeable`.
- Lớp kế thừa từ một lớp đã triển khai `AutoCloseable`.
- Biến được khai báo bằng `AutoCloseable`, `Closeable` hoặc một kiểu con phù hợp và có đối tượng tương thích.

Các trường hợp **không đủ điều kiện**:

```java
class HasCloseMethod {
    public void close() {
        System.out.println("closed");
    }
}

// Không biên dịch: HasCloseMethod không triển khai AutoCloseable.
// try (HasCloseMethod resource = new HasCloseMethod()) {
//     System.out.println("work");
// }
```

Chỉ sở hữu một phương thức `close()` giống chữ ký không khiến lớp tự động là `AutoCloseable`. Java dùng **kiểu định danh** cho interface: lớp phải có quan hệ `implements`/`extends` phù hợp. Tương tự, nếu một đối tượng thực tế là `AutoCloseable` nhưng bạn lưu nó trong biến kiểu `Object`, biến đó không tự được phép đưa vào phần tài nguyên mà không biểu diễn đúng kiểu. Giải pháp tốt hơn là khai báo biến/kiểu API bằng `AutoCloseable` hay một kiểu con ngay từ đầu, thay vì ép kiểu thiếu an toàn.

## 3. Tự viết lớp triển khai `AutoCloseable`

Giả sử một đối tượng quản lý tài nguyên có thể đóng, cần làm hai việc:

1. Khai báo `implements AutoCloseable` và triển khai `public void close()`.
2. Trong `close()`, **thực sự giải phóng hoặc hoàn tất** tài nguyên do đối tượng chịu trách nhiệm quản lý; chỉ in thông điệp không đủ cho một lớp quản lý tài nguyên thật.

Ví dụ tối giản dùng để quan sát thứ tự hoạt động:

```java
class TrackedResource implements AutoCloseable {
    private final String name;

    TrackedResource(String name) {
        this.name = name;
        System.out.println("open " + name);
    }

    void work() {
        System.out.println("work " + name);
    }

    @Override
    public void close() {
        System.out.println("close " + name);
    }
}
```

Đây là **lớp minh họa**, chưa phải chương trình chạy độc lập; chương trình hoàn chỉnh xuất hiện ở mục 6. Vì `close()` trong ví dụ không ném checked exception, lớp có thể **không khai báo `throws Exception`** dù chữ ký của `AutoCloseable.close()` có khai báo.

Dùng lớp trong `try-with-resources`:

```java
try (TrackedResource resource = new TrackedResource("A")) {
    resource.work();
} // Java tự gọi resource.close() ở đây
```

Đầu ra:

```text
open A
work A
close A
```

Từ khóa `@Override` giúp compiler xác nhận bạn đang triển khai phương thức giao diện đúng chữ ký. `close()` nên được thiết kế rõ ràng: nếu không thể giải phóng tài nguyên, nên biểu đạt lỗi theo hợp đồng API thay vì âm thầm che giấu. Giao diện `AutoCloseable` **không tự triển khai hành vi đóng**; nhà phát triển lớp vẫn phải cài đặt đúng.

### `close()` không bắt buộc ném `Exception`

Ba kiểu triển khai sau đều có thể hợp lệ về chữ ký, với yêu cầu là phần thân đúng:

```java
class SilentClose implements AutoCloseable {
    @Override
    public void close() {
        // Đóng tài nguyên mà không khai báo checked exception.
    }
}

class FileLikeClose implements AutoCloseable {
    @Override
    public void close() throws java.io.IOException {
        // Khi thất bại có thể ném IOException.
    }
}

class BroadClose implements AutoCloseable {
    @Override
    public void close() throws Exception {
        // Cho phép báo lỗi checked Exception theo hợp đồng rộng.
    }
}
```

Một phương thức override được phép khai báo **ít loại checked exception hơn**, hoặc không khai báo checked exception nào, so với `AutoCloseable.close()`. Khi thiết kế API, nên dùng loại ngoại lệ càng cụ thể càng tốt. Không cần ghi `throws Exception` chỉ vì giao diện gốc khai báo như vậy.

## 4. Điều kiện của phần tài nguyên trong `try (...)`

### 4.1. Khai báo và khởi tạo tài nguyên ngay trong ngoặc

Cú pháp cơ bản:

```java
try (TrackedResource resource = new TrackedResource("A")) {
    resource.work();
}
```

Tài nguyên được tạo **trước khi chạy thân `try`**, rồi tự động được đóng khi vùng tài nguyên kết thúc. Khi khai báo như vậy, biến tài nguyên trong phạm vi quản lý được xem là `final`: không thể gán lại `resource` sang đối tượng khác bên trong khối. Tuy nhiên, đối tượng mà `resource` trỏ đến vẫn có thể có trạng thái thay đổi và có thể thực hiện các phương thức hợp lệ.

Một biểu thức bình thường không được coi là khai báo tài nguyên nếu nó không đúng dạng cú pháp của phần tài nguyên. Ví dụ `try (new TrackedResource("A"))` không phải cú pháp khai báo tài nguyên hợp lệ cho trường hợp này: hãy dùng biến tài nguyên `try (TrackedResource r = new TrackedResource("A"))`.

### 4.2. Dùng nhiều tài nguyên

Các khai báo được ngăn bằng **dấu chấm phẩy `;`**, không dùng dấu phẩy:

```java
try (TrackedResource first = new TrackedResource("A");
     TrackedResource second = new TrackedResource("B")) {
    second.work();
}
```

Các tài nguyên được **khởi tạo từ trái sang phải** và **đóng theo thứ tự ngược lại**: đóng `B` trước, rồi đóng `A`. Điều này hữu ích khi tài nguyên phía sau phụ thuộc vào tài nguyên phía trước.

```text
open A
open B
work B
close B
close A
```

Nếu khởi tạo tài nguyên thứ hai thất bại, những tài nguyên trước đó đã khởi tạo thành công vẫn được hệ thống đóng. Một đối tượng mà quá trình khởi tạo chưa thành công sẽ không được tự động đóng như một tài nguyên đã khai báo thành công; constructor/factory phải quản lý việc dọn dẹp phần tài nguyên nội bộ mà nó đã lấy được trước khi thất bại.

### 4.3. Dùng biến có sẵn (Java 9+)

Từ Java 9, có thể đưa **biến tài nguyên đã tồn tại** vào ngoặc `try` nếu đó là biến `final` hoặc *effectively final* (được gán giá trị theo cách thỏa quy tắc, và không bị gán lại):

```java
TrackedResource existing = new TrackedResource("C");

try (existing) {
    existing.work();
}
```

Biến `existing` được khai báo trước và không bị gán lại, nên hợp lệ trên Java 9+. Sau khi kết thúc `try`, biến vẫn tồn tại nếu còn trong phạm vi, nhưng **đối tượng đã được đóng**; không được giả định có thể dùng lại tài nguyên đang mở. Nếu bạn gán lại `existing` trước hoặc sau `try` theo cách khiến nó không còn effectively final, cú pháp này có thể không biên dịch.

**Phân biệt phiên bản:** Java 7 giới thiệu `try-with-resources` với khai báo tài nguyên trong ngoặc. Cú pháp viết ngắn `try (existing)` được bổ sung ở Java 9. Cả hai đều còn được dùng trên Java 17+ và các phiên bản Java hiện đại.

### 4.4. Dùng `var` (Java 10+)

Khi kiểu có thể suy luận rõ ràng, biến cục bộ khai báo trong ngoặc có thể dùng `var`:

```java
try (var resource = new TrackedResource("D")) {
    resource.work();
}
```

`var` không làm thay đổi điều kiện kiểu: kiểu được suy luận vẫn phải là `AutoCloseable` hoặc kiểu con, và đối tượng vẫn được đóng tự động. Nên giữ tên biến và kiểu rõ ràng nếu điều đó giúp người đọc hiểu API hơn.

### 4.5. Tài nguyên bằng `null`

Một biến tài nguyên được khởi tạo `null` **không bị gọi `close()`**, nên chỉ riêng cơ chế đóng này không ném `NullPointerException`:

```java
try (TrackedResource resource = null) {
    System.out.println("body");
}
```

Đoạn trên in `body` rồi thoát; không có dòng `close ...`. Nhưng nếu thân `try` cố gọi `resource.work()` thì vẫn có `NullPointerException` như mọi tham chiếu `null` khác. Trong thiết kế thông thường, nên kiểm tra/đảm bảo tài nguyên không `null` thay vì dựa vào ngoại lệ đặc biệt này.

## 5. `AutoCloseable` và `Closeable`: quan hệ kiểu và checked exception

`java.io.Closeable` **kế thừa `AutoCloseable`**, với hợp đồng `close()` thường hẹp hơn:

```java
public interface Closeable extends AutoCloseable {
    @Override
    void close() throws java.io.IOException;
}
```

Đây là **minh họa chữ ký**, không phải mã tự khai báo lại interface tiêu chuẩn.

| Đặc điểm | `AutoCloseable` | `java.io.Closeable` |
| --- | --- | --- |
| Gói | `java.lang` | `java.io` |
| Phương thức chính | `void close() throws Exception` | `void close() throws IOException` |
| Tương thích `try-with-resources` | Có | Có vì kế thừa `AutoCloseable` |
| Hành vi gọi `close()` lặp | Giao diện không bắt buộc idempotent | Hợp đồng `Closeable` quy định đóng lại sau khi đã đóng không có tác dụng |
| Định hướng dùng | Giao diện tổng quát cho mọi loại tài nguyên | Đặc biệt phù hợp với tài nguyên I/O |

Ví dụ các đối tượng đủ điều kiện thực tế trong JDK:

- `BufferedReader`, `InputStream`, `OutputStream`, `Reader`, `Writer`, `ZipFile` là các kiểu có thể đóng trong nhóm I/O (trực tiếp hoặc qua `Closeable`).
- `java.sql.Connection`, `Statement` và `ResultSet` đều tương thích `AutoCloseable`; tùy API, `close()` có thể khai báo `SQLException`.
- `java.util.stream.Stream` cũng hỗ trợ đóng, nhưng **không phải mọi Stream đều sở hữu tài nguyên cần đóng**. Một stream tạo từ nguồn I/O như `Files.lines(...)` cần được quản lý theo hợp đồng API.

Khi khai báo kiểu tĩnh rất rộng như `AutoCloseable`, compiler phải xét rằng `close()` **có thể ném `Exception`**:

```java
static void broadType(AutoCloseable resource) throws Exception {
    try (resource) { // Java 9+, resource là tham số effectively final.
        System.out.println("using");
    }
}
```

Nếu biết tài nguyên chỉ có khả năng ném `IOException` khi đóng, sử dụng kiểu có chữ ký hẹp phù hợp sẽ cho hợp đồng checked exception rõ hơn. Không nên ép kiểu tùy tiện chỉ để bỏ kiểm tra checked exception; hãy chọn kiểu và phương thức `close()` chính xác ngay khi thiết kế lớp.

## 6. Ví dụ đầy đủ Java 17+: thứ tự đóng và suppressed exception

Chương trình sau kết hợp **hai tài nguyên được đóng theo thứ tự ngược**, **tài nguyên có sẵn**, và **tình huống thân `try` cùng `close()` đều thất bại**. Phần `Tracked` chỉ in trạng thái nhằm quan sát hành vi, còn `Faulty` cố tình ném `IOException` để minh họa cách Java giữ nguyên nhân.

Tạo tệp **`AutoCloseableDemo.java`**:

```java
import java.io.IOException;

public class AutoCloseableDemo {

    static final class Tracked implements AutoCloseable {
        private final String name;

        Tracked(String name) {
            this.name = name;
            System.out.println("open " + name);
        }

        void work() {
            System.out.println("work " + name);
        }

        @Override
        public void close() {
            System.out.println("close " + name);
        }
    }

    static final class Faulty implements AutoCloseable {
        void work() throws IOException {
            throw new IOException("work failed");
        }

        @Override
        public void close() throws IOException {
            System.out.println("close faulty");
            throw new IOException("close failed");
        }
    }

    public static void main(String[] args) {
        try (Tracked first = new Tracked("A");
             Tracked second = new Tracked("B")) {
            second.work();
        }

        Tracked reused = new Tracked("C");
        try (reused) {
            reused.work();
        }

        try (Faulty faulty = new Faulty()) {
            faulty.work();
        } catch (IOException ex) {
            System.out.println("primary: " + ex.getMessage());
            for (Throwable suppressed : ex.getSuppressed()) {
                System.out.println("suppressed: "
                        + suppressed.getMessage());
            }
        }
    }
}
```

Chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 AutoCloseableDemo.java
java AutoCloseableDemo
```

**Stdout chính xác:**

```text
open A
open B
work B
close B
close A
open C
work C
close C
close faulty
primary: work failed
suppressed: close failed
```

Phân tích:

1. `first` rồi `second` được tạo theo thứ tự; khi thoát khối, `second.close()` được gọi trước `first.close()`.
2. Biến `reused` tạo ngoài ngoặc và không bị gán lại. `try (reused)` hợp lệ vì Java 9+ cho phép biến tài nguyên existing effectively final.
3. `faulty.work()` ném `IOException("work failed")`. Khi rời thân `try`, Java **vẫn gọi `faulty.close()`**, và `close()` tiếp tục ném `IOException("close failed")`.
4. Trong trường hợp này, lỗi ở thân `try` được giữ làm ngoại lệ **chính**; lỗi khi đóng được đính kèm vào danh sách **suppressed exceptions** của lỗi chính. Phương thức `ex.getSuppressed()` trả những ngoại lệ bị đính kèm.
5. Nếu thân `try` thành công nhưng `close()` thất bại, lỗi khi đóng có thể trở thành ngoại lệ thoát ra chính, chứ không nhất thiết là suppressed.

Chương trình cố tình không mở tệp thật hoặc kết nối thật, để bạn có thể biên dịch và chạy ở bất kỳ môi trường JDK 17+ nào mà không cần cấu hình bên ngoài.

## 7. Khi nào `close()` được gọi và thứ tự xử lý lỗi?

`try-with-resources` bảo đảm theo ngữ nghĩa Java thông thường rằng khi điều khiển rời khỏi thân `try`, hệ thống thực hiện việc đóng tài nguyên đã khởi tạo thành công:

- Thân `try` chạy hết bình thường.
- Thân `try` ném exception.
- Thân `try` thực hiện `return`, `break` hoặc `continue` hợp lệ theo cấu trúc điều khiển.
- Khởi tạo một tài nguyên **sau** thất bại: những tài nguyên trước đó đã khởi tạo thành công được đóng.
- Có nhiều tài nguyên: chúng được đóng từ phải sang trái.

Quy tắc áp dụng trong luồng thực thi bình thường của JVM. Không nên diễn giải thành “luôn đóng ngay cả khi tiến trình bị hệ điều hành giết, JVM bị chấm dứt cưỡng bức hoặc máy mất điện”. Đó là lý do tài nguyên quan trọng vẫn cần cơ chế khôi phục hệ thống khi cần.

### Ngoại lệ từ thân `try` và từ `close()`

| Tình huống | Ngoại lệ chính | Ngoại lệ suppressed |
| --- | --- | --- |
| Thân và `close` đều thành công | Không có | Không có |
| Thân ném lỗi, `close` thành công | Lỗi từ thân | Không có do đóng |
| Thân thành công, `close` ném lỗi | Lỗi từ `close` | Thường không có do thân |
| Thân và `close` đều ném lỗi | Lỗi từ thân | Lỗi từ `close` |
| Đóng nhiều tài nguyên và có nhiều lỗi đóng | Lỗi phát sinh đầu tiên trong quá trình đóng, nếu không có lỗi từ thân | Lỗi đóng tiếp theo được đính kèm |

Bạn có thể đọc `Throwable.getSuppressed()` để phân biệt lỗi xuất hiện khi đóng. Trong ứng dụng thực tế, logging framework có thể in chuỗi suppressed khi hiển thị stack trace, nhưng đừng giả định mọi hệ thống log đều hiện các lỗi đó nếu không kiểm tra cấu hình.

### `catch` và `finally` diễn ra sau khi đóng

Với dạng:

```java
try (Tracked r = new Tracked("X")) {
    r.work();
} catch (RuntimeException ex) {
    System.err.println("failed");
} finally {
    System.out.println("finally");
}
```

Java gọi `r.close()` **trước khi** thực thi `catch`/`finally` gắn với câu lệnh `try-with-resources` đó. Vì vậy, khi cần log trạng thái lỗi đóng, `catch` đã nhận được ngoại lệ chính và danh sách suppressed nếu có. Đoạn minh họa trên phải được đặt trong cùng lớp có định nghĩa `Tracked`.

### Trường hợp có ngoại lệ trong lúc tạo tài nguyên

```text
Khởi tạo A thành công
Khởi tạo B thành công
Khởi tạo C thất bại
    |
    +--> đóng B
    +--> đóng A
    +--> chuyển lỗi ra catch/điểm gọi
```

Khối thân `try` không bắt đầu nếu một trong các tài nguyên chưa tạo được, nhưng các tài nguyên đã tạo trước đó vẫn được xử lý đóng. Nếu constructor của chính đối tượng C đã mở một tài nguyên nội bộ rồi ném lỗi *trước khi hoàn tất tạo đối tượng*, constructor đó phải chủ động dọn dẹp phần đã mở; không thể dựa vào `close()` của một đối tượng chưa được đăng ký thành công trong phần tài nguyên.

## 8. Điều kiện biên dịch và các lỗi thường gặp

| Cách viết / giả định | Kết quả | Cách đúng |
| --- | --- | --- |
| `try (String s = "text") { ... }` | Không biên dịch: `String` không phải `AutoCloseable` | Chọn lớp triển khai `AutoCloseable` |
| Lớp chỉ có phương thức `close` nhưng không `implements AutoCloseable` | Không đủ điều kiện kiểu | Triển khai `AutoCloseable` hoặc dùng kiểu con |
| `class X implements AutoCloseable` nhưng quên triển khai `close()` ở lớp cụ thể | Không biên dịch, trừ khi là lớp `abstract` hoặc kế thừa triển khai hợp lệ | Thêm `public void close()` |
| `close()` không `public` | Không thể thực hiện đúng phương thức giao diện `public` | Khai báo `public void close()` |
| `try (int number = 1)` | `int` không phải tài nguyên đóng được | Đưa biến số thông thường vào thân `try`, không đặt ở phần tài nguyên |
| `try (first, second)` | Dấu phẩy không phải dấu phân tách tài nguyên | Dùng `;` giữa các khai báo/biểu thức tài nguyên |
| `try (resource)` với biến bị gán lại | Có thể không biên dịch vì biến không effectively final | Dùng biến ổn định hoặc khai báo tài nguyên mới trong `try (...)` |
| Không bắt/khai báo `Exception` khi resource có kiểu `AutoCloseable` chung | Compiler có thể báo checked exception từ `close()` | Xử lý/khai báo đúng các lỗi của `close()` theo kiểu tĩnh |
| Cho rằng `close()` được gọi theo thứ tự khai báo | Sai khi có nhiều tài nguyên | Đóng theo thứ tự ngược |
| Chỉ ghi log ngoại lệ chính, bỏ qua suppressed | Mất thông tin lỗi khi đóng | Kiểm tra `getSuppressed()` khi chẩn đoán |
| Dùng `List` hoặc `String` như tài nguyên vì “có dữ liệu” | Collection/chuỗi thường không quản lý tài nguyên cần đóng | Chỉ đưa đối tượng đóng được theo hợp đồng `AutoCloseable` |
| Giả định `AutoCloseable.close()` luôn idempotent | Giao diện tổng quát không yêu cầu | Thiết kế cụ thể phải định nghĩa hành vi đóng lặp |

**Lưu ý quan trọng về checked exception:** Dù `AutoCloseable.close()` khai báo `throws Exception`, lớp của bạn có thể override với `throws IOException` hoặc không `throws`. Compiler xét kiểu của biến tài nguyên và chữ ký `close()` của kiểu đó. Vì thế, khi thiết kế kiểu riêng, khai báo ngoại lệ hẹp vừa đủ thường giúp code sử dụng `try-with-resources` dễ kiểm tra hơn.

Không nên thay try-with-resources bằng việc dựa vào `finalize()` hoặc chờ bộ thu gom rác: thu gom rác không có nghĩa việc đóng tài nguyên sẽ diễn ra đúng thời điểm, còn finalization là cơ chế không thích hợp cho quản lý tài nguyên hiện đại. Cách quản lý rõ ràng là đóng có cấu trúc qua `try-with-resources`.

## 9. Thiết kế `AutoCloseable` đúng cho tài nguyên thật

Khi tạo lớp quản lý socket, giao dịch, stream hoặc một phiên làm việc, việc `implements AutoCloseable` mới là **điều kiện cú pháp**. Phần quan trọng hơn là **hợp đồng vòng đời**:

1. **Quyền sở hữu rõ ràng:** đối tượng `close()` được quyền giải phóng những tài nguyên nào? Nếu nhiều đối tượng cùng chia sẻ một tài nguyên, không để một phía đóng bất ngờ khiến phía kia hỏng.
2. **Đóng đúng thứ tự:** nếu một tài nguyên bao bọc tài nguyên khác, quy định đối tượng nào chịu trách nhiệm đóng đối tượng bên dưới. Tránh đóng trùng khi đã giao ownership cho wrapper.
3. **Giới hạn sử dụng sau đóng:** đa số tài nguyên có trạng thái "closed"; các phương thức sử dụng cần kiểm tra trạng thái và báo lỗi phù hợp. Giao diện `AutoCloseable` không tự bảo vệ đối tượng khỏi bị gọi sau đóng.
4. **Đóng lại:** cân nhắc cài đặt idempotent để tránh giải phóng lặp hoặc phát sinh lỗi khó đoán. Đây là *khuyến nghị thiết kế*, không phải yêu cầu bắt buộc của `AutoCloseable`.
5. **Báo lỗi đúng kiểu:** nếu đóng thất bại, chọn checked/unchecked exception phù hợp; giữ ngữ cảnh để có thể chẩn đoán, nhưng không lạm dụng `throws Exception` quá rộng.
6. **An toàn luồng:** `try-with-resources` tự quản lý phạm vi một lời gọi, **không tự làm đối tượng thread-safe**. Nếu tài nguyên được chia sẻ giữa các luồng, cần quy tắc phối hợp và ownership riêng.
7. **Khởi tạo thất bại:** nếu constructor/factory chiếm giữ nhiều tài nguyên rồi thất bại giữa chừng, phải dọn dẹp phần đã mở trước khi ném lỗi; không giao trách nhiệm này cho `try` khi chưa trả về tài nguyên thành công.

Mẫu triển khai trạng thái đơn giản:

```java
class SessionResource implements AutoCloseable {
    private boolean closed;

    void doWork() {
        if (closed) {
            throw new IllegalStateException("Resource already closed");
        }
        // Xử lý tài nguyên thực tế.
    }

    @Override
    public void close() {
        if (closed) {
            return;
        }
        closed = true;
        // Giải phóng tài nguyên do đối tượng sở hữu.
    }
}
```

Đoạn trên là **khung minh họa**, chưa quản lý tài nguyên I/O thực. Trạng thái `closed` giúp thể hiện vòng đời; khi làm việc với tài nguyên thật, cần quyết định khi nào đánh dấu đã đóng, xử lý lỗi giải phóng từng bước, và đồng bộ truy cập nếu có nhiều luồng. Không nên dùng đoạn này như thư viện tài nguyên hoàn chỉnh nếu chưa triển khai chính sách đóng cụ thể.

## 10. Bài tập thực hành và đáp án

**Bài 1.** Lớp sau có đủ điều kiện dùng trong try-with-resources không?

```java
class Timer {
    public void close() {
        System.out.println("done");
    }
}
```

**Bài 2.** Viết lớp `TimerResource` đủ điều kiện dùng trong `try (...)`, tự in `"closed"` khi đóng và không khai báo checked exception.

**Bài 3.** Đoán thứ tự đầu ra:

```java
try (Tracked a = new Tracked("A");
     Tracked b = new Tracked("B")) {
    System.out.println("body");
}
```

**Bài 4.** Tại sao một tài nguyên có kiểu khai báo `AutoCloseable` có thể khiến compiler yêu cầu `throws Exception`, trong khi cùng đối tượng đó được truy cập qua kiểu cụ thể có `close()` không khai báo checked exception thì không?

**Bài 5.** Thân `try` ném `IOException("read failed")`, còn `close()` ném `IOException("close failed")`. Lỗi nào là ngoại lệ chính? Tìm lỗi còn lại bằng phương thức nào?

**Bài 6.** Có thể dùng `try (existing)` với biến local đã tạo trước khối `try` trên Java 17 không? Điều kiện về phép gán lại là gì?

### Đáp án

1. **Không.** Lớp `Timer` chỉ có phương thức tên `close` mà không triển khai `AutoCloseable` hay kiểu con; điều kiện kiểu không được đáp ứng.
2. Ví dụ:

   ```java
   class TimerResource implements AutoCloseable {
       @Override
       public void close() {
           System.out.println("closed");
       }
   }
   ```

   Dùng `try (TimerResource timer = new TimerResource()) { ... }` để Java tự gọi `close()`.
3. `open A`, `open B`, `body`, `close B`, `close A` theo đúng thứ tự tạo trái–phải và đóng phải–trái của lớp `Tracked` trong ví dụ hoàn chỉnh.
4. Compiler xét **kiểu tĩnh** của tài nguyên. `AutoCloseable.close()` khai báo `throws Exception`, nhưng override ở lớp cụ thể có thể hẹp hơn hoặc không ném checked exception.
5. `read failed` là ngoại lệ chính; `close failed` được đính kèm, xem qua `ex.getSuppressed()`.
6. **Có từ Java 9 trở lên** (Java 17 đáp ứng). Biến có sẵn phải là `final` hoặc *effectively final*, nghĩa là không bị gán lại theo cách làm mất điều kiện của biến tài nguyên.

**Tổng kết:** Tài nguyên của `try-with-resources` phải có kiểu triển khai `AutoCloseable` (hoặc kiểu con), chứ không chỉ có phương thức tên `close()`. Phương thức `close()` thực sự phải quản lý vòng đời tài nguyên. Java tự đóng các tài nguyên đã khởi tạo thành công khi rời vùng `try`, theo thứ tự ngược, và giữ lỗi đóng trong **suppressed exceptions** khi phù hợp. Từ Java 7 đến Java hiện đại, đây vẫn là cách chuẩn, rõ ràng để quản lý vòng đời tài nguyên có thể đóng.