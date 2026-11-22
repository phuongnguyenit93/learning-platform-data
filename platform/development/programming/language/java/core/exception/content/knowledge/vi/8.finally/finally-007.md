# Ngoại lệ cleanup che mất ngoại lệ ban đầu trong Java

Một thao tác có thể thất bại **hai lần**: lần đầu khi thực hiện công việc chính, lần thứ hai khi dọn dẹp tài nguyên. Ví dụ, chương trình đang ghi dữ liệu thì gặp lỗi, sau đó lệnh đóng kết nối cũng ném exception. Nếu việc dọn dẹp được viết không cẩn thận trong khối `finally`, **ngoại lệ mới của cleanup có thể thay thế ngoại lệ ban đầu**, khiến caller chỉ nhìn thấy “không đóng được” mà không thấy “ghi dữ liệu thất bại”.

Đây là vấn đề **exception masking** hoặc **exception suppression không đúng cách** theo nghĩa thông thường: *nguyên nhân lỗi quan trọng nhất bị che khuất bởi một lỗi phát sinh sau đó*. Cần phân biệt hiện tượng “che mất” với cơ chế **suppressed exceptions** chính thức của Java. `try-with-resources` được thiết kế để giữ ngoại lệ chính và đính kèm ngoại lệ khi đóng tài nguyên vào danh sách phụ thông qua `Throwable.getSuppressed()`.

Bài này phân tích chính xác quy tắc luồng điều khiển của `finally`, ví dụ Java 17 có thể biên dịch/chạy, cách đọc thông tin lỗi, cách sửa bằng `try-with-resources`, và trường hợp buộc phải tự xử lý cleanup.

## 1. Tình huống dẫn đến ngoại lệ bị che khuất

Hình dung một thao tác:

1. Mở tài nguyên.
2. Thực hiện công việc chính: đọc dữ liệu, gửi yêu cầu, ghi tệp hoặc cập nhật cơ sở dữ liệu.
3. Công việc chính thất bại và ném ngoại lệ A.
4. Khi rời phạm vi, cleanup cũng thất bại và ném ngoại lệ B.
5. Caller cần biết cả hai, **đặc biệt A**, vì A mô tả lý do công việc chính thất bại.

Nếu mã được viết theo mẫu:

```java
try {
    doWork();
} finally {
    closeResource();
}
```

đây chỉ là **mã khung**, giả sử cả hai phương thức đã được định nghĩa. Nếu `doWork()` ném A rồi `closeResource()` ném B từ `finally`, **B trở thành exception được truyền ra từ toàn bộ cấu trúc**. A không tự động được gắn thành `cause` hay `suppressed` của B.

Điều này gây hậu quả:

- Stack trace bên ngoài có thể hướng người vận hành tới `closeResource()` trong khi lỗi đầu tiên thực sự xảy ra ở `doWork()`.
- Thao tác có thể ghi dở, gửi dở hoặc chưa hoàn tất, nhưng việc phân tích chỉ tập trung vào cleanup.
- Các mã xử lý theo loại exception có thể nhận B thay vì A, dẫn tới retry, rollback hoặc phản hồi sai.
- Nếu hệ thống không lưu A trước đó, việc tái dựng nguyên nhân gốc trở nên khó khăn.

**Đừng hiểu rằng `finally` luôn làm mất lỗi gốc.** Nếu `finally` hoàn tất bình thường, A tiếp tục lan truyền. Việc che khuất xảy ra khi `finally` **kết thúc bất thường bằng một lý do mới** như ném exception mới hoặc thực hiện một dạng điều khiển luồng thay thế.

## 2. Quy tắc ngôn ngữ: lý do hoàn tất sau cùng

Một khối `try` có thể kết thúc **bình thường** hoặc **bất thường** (abrupt completion), chẳng hạn vì `throw`, `return`, `break` hay `continue`. Khi có `finally`, Java thực thi `finally` trước khi hoàn tất việc rời cấu trúc theo đường thông thường.

Hai trường hợp cần phân biệt:

| Tình huống | `finally` làm gì? | Kết quả tiếp theo |
| --- | --- | --- |
| `try` hoàn tất bình thường | `finally` hoàn tất bình thường | Chạy câu lệnh sau cấu trúc |
| `try` ném A | `finally` hoàn tất bình thường | A tiếp tục lan truyền |
| `try` ném A | `finally` ném B | B thay thế A như lý do thoát ra |
| `catch` ném lại A | `finally` ném B | B thay thế A |
| `try` chuẩn bị `return` giá trị V | `finally` hoàn tất bình thường | Trả V |
| `try` chuẩn bị `return` giá trị V | `finally` ném B | Không trả V; ném B |
| `try` ném A | `finally` thực hiện `return` | Exception A bị che; phương thức trả về |
| `try` ném A | `finally` thực hiện `break` hoặc `continue` hợp lệ | Điều khiển luồng từ `finally` có thể thay thế việc ném A |

Một cách nhớ ngắn: **kết quả đang chờ từ `try/catch` chỉ được giữ khi `finally` hoàn tất bình thường**. Nếu `finally` kết thúc bất thường, lý do kết thúc mới của `finally` thường thắng.

Quy tắc này không liên quan checked hay unchecked: A và B có thể đều là `RuntimeException`, hoặc một/both là checked exception. Nghĩa vụ `throws` thay đổi theo kiểu exception, nhưng hiện tượng masking là về **luồng thực thi**.

## 3. Ví dụ độc lập: cleanup làm mất ngoại lệ gốc

Lưu tệp **`FinallyMasksExceptionDemo.java`**:

```java
public class FinallyMasksExceptionDemo {
    static void perform() {
        try {
            System.out.println("Đang xử lý");
            throw new IllegalArgumentException("Dữ liệu đầu vào sai");
        } finally {
            System.out.println("Đang cleanup");
            throw new IllegalStateException("Không đóng được tài nguyên");
        }
    }

    public static void main(String[] args) {
        try {
            perform();
        } catch (RuntimeException e) {
            System.out.println("Caller nhận: "
                    + e.getClass().getSimpleName());
            System.out.println("Message: " + e.getMessage());
            System.out.println("Cause null: " + (e.getCause() == null));
            System.out.println("Suppressed: " + e.getSuppressed().length);
        }
        System.out.println("Main tiếp tục");
    }
}
```

Biên dịch và chạy với Java 17+:

```bash
javac -encoding UTF-8 --release 17 FinallyMasksExceptionDemo.java
java FinallyMasksExceptionDemo
```

**Stdout chính xác** khi console hiển thị UTF-8:

```text
Đang xử lý
Đang cleanup
Caller nhận: IllegalStateException
Message: Không đóng được tài nguyên
Cause null: true
Suppressed: 0
Main tiếp tục
```

Phân tích từng bước:

1. Thân `try` ném `IllegalArgumentException` với message “Dữ liệu đầu vào sai”.
2. Trước khi exception được đẩy ra khỏi `perform()`, Java đi vào `finally`.
3. `finally` lại ném `IllegalStateException` với message “Không đóng được tài nguyên”.
4. `perform()` thoát ra với **`IllegalStateException`**, không phải `IllegalArgumentException` ban đầu.
5. `getCause() == null` và `getSuppressed().length == 0` vì không có mã nào liên kết hai ngoại lệ. **`finally` không tự tạo `cause` hoặc `suppressed`.**

`main` bắt `RuntimeException` nên xử lý được B và tiếp tục sau handler. Nếu caller chỉ viết `catch (IllegalArgumentException e)`, nó **không** bắt được B; điều này có thể khiến lỗi đi xa hơn dự kiến.

> Đây là **phản ví dụ có chủ đích** nhằm phơi bày masking. Không viết cleanup luôn ném exception như vậy trong ứng dụng thực.

## 4. Nếu `finally` không ném gì, lỗi gốc vẫn tồn tại

Ngược lại, `finally` hoàn tất bình thường thì ngoại lệ ban đầu không bị thay thế. Chương trình độc lập **`FinallyKeepsExceptionDemo.java`**:

```java
public class FinallyKeepsExceptionDemo {
    static void perform() {
        try {
            System.out.println("Work");
            throw new IllegalArgumentException("Lỗi gốc");
        } finally {
            System.out.println("Cleanup hoàn tất");
        }
    }

    public static void main(String[] args) {
        try {
            perform();
        } catch (IllegalArgumentException e) {
            System.out.println("Caller: " + e.getMessage());
        }
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 --release 17 FinallyKeepsExceptionDemo.java
java FinallyKeepsExceptionDemo
```

**Stdout chính xác:**

```text
Work
Cleanup hoàn tất
Caller: Lỗi gốc
```

Handler ngoài nhận đúng `IllegalArgumentException`. Sự khác biệt với ví dụ trước chỉ nằm ở chỗ `finally` **hoàn tất bình thường**.

Một lưu ý sâu hơn: nếu `finally` gọi một phương thức cleanup và phương thức đó âm thầm **nuốt lỗi cleanup** rồi trả về bình thường, A vẫn đi lên caller nhưng B có thể bị mất. Điều này không masking A, nhưng vẫn có thể khiến chẩn đoán bỏ sót lỗi phụ. Nên có chính sách ghi nhận B phù hợp.

## 5. Trường hợp `catch` đã ném lại nhưng `finally` vẫn che mất

Việc đã bắt và ném lại A bằng `throw e;` **không bảo đảm caller nhận A** nếu phần `finally` sau đó ném B.

Ví dụ:

```java
try {
    doWork();
} catch (IllegalArgumentException e) {
    System.out.println("Ghi nhận lỗi gốc: " + e.getMessage());
    throw e;
} finally {
    closeResource(); // Nếu ném B, B có thể thay A.
}
```

Đây là **mã khung**, giả sử `doWork()` và `closeResource()` đã được định nghĩa. Trình tự khi cả hai thao tác thất bại:

```text
doWork()                 → throw A
catch                   → nhận A, định ném lại A
finally                 → closeResource() throw B
caller                  → nhận B
```

Bản thân `throw e` không tạo exception mới; nó giữ tham chiếu gốc. Nhưng do `finally` kết thúc bất thường, **kết quả ném lại đang chờ bị thay thế**.

Ngoài ra, exception được ném từ **thân `catch`** không được thử bắt bởi các nhánh `catch` đứng sau cùng cấu trúc. Khi `finally` ném B, B tìm handler ở một cấu trúc bao ngoài/caller, không quay lại các handler cùng cấp bên trong.

## 6. Không chỉ `throw`: `return` trong `finally` cũng che lỗi

Một sai lầm nguy hiểm là `return` từ `finally`. Nó có thể khiến chương trình **trả kết quả trông như thành công dù `try` đã ném exception**.

Lưu `FinallyReturnMaskDemo.java`:

```java
public class FinallyReturnMaskDemo {
    static int maskedFailure() {
        try {
            throw new IllegalArgumentException("Không tính được");
        } finally {
            return 10; // Phản ví dụ: nuốt lỗi gốc!
        }
    }

    static int maskedReturn() {
        try {
            return 20;
        } finally {
            return 30; // Phản ví dụ: ghi đè kết quả.
        }
    }

    public static void main(String[] args) {
        System.out.println("Lỗi bị che: " + maskedFailure());
        System.out.println("Return bị ghi đè: " + maskedReturn());
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 --release 17 FinallyReturnMaskDemo.java
java FinallyReturnMaskDemo
```

**Stdout chính xác:**

```text
Lỗi bị che: 10
Return bị ghi đè: 30
```

Với `maskedFailure()`, một `IllegalArgumentException` thực sự được ném trong `try`, nhưng `finally` trả về `10` và **không có exception nào thoát ra tới caller**. Với `maskedReturn()`, `return 30` của `finally` thắng `return 20` đang chờ.

Java cho phép cú pháp trong các phương thức kiểu này, nhưng thiết kế rất khó kiểm tra và dễ che giấu sự cố. Quy tắc thực hành: **không `return`, `break` hoặc `continue` từ `finally` trừ khi có lý do đặc biệt được kiểm soát chặt**; cleanup nên hoàn tất bình thường trong khả năng cho phép.

## 7. Giải pháp ưu tiên: `try-with-resources`

Từ Java 7, `try-with-resources` giúp quản lý những đối tượng thực hiện giao diện `AutoCloseable`. Tài nguyên được khai báo trong phần `try (...)` sẽ được Java **cố gắng đóng** khi rời khối, kể cả khi có exception.

Điểm khác biệt lớn nhất với việc `finally` ném lỗi thủ công:

- Nếu **thân `try` ném A**, rồi `close()` ném B, Java thường giữ **A làm exception chính**.
- **B được gắn vào A dưới dạng suppressed exception**, truy cập bằng `A.getSuppressed()`.
- Nếu thân `try` kết thúc bình thường nhưng `close()` ném B, **B có thể trở thành exception chính**.
- Nếu nhiều tài nguyên được khai báo, Java đóng chúng theo **thứ tự ngược** với thứ tự khai báo.
- Nếu nhiều lỗi đóng xảy ra khi A đang lan truyền, các lỗi đóng được đính kèm theo thứ tự đóng, thay vì thay thế A.

Điều này giúp giữ lại bằng chứng của cả lỗi chính và lỗi cleanup, tránh hiện tượng lỗi sau che mất lỗi trước.

### `cause` khác `suppressed`

| Thuộc tính | Cách thiết lập phổ biến | Ý nghĩa |
| --- | --- | --- |
| `getCause()` | Constructor như `new IllegalStateException("...", cause)`, hoặc `initCause` hợp lệ | Một lỗi **gây ra** exception hiện tại khi bọc/chuyển tầng |
| `getSuppressed()` | `try-with-resources` hoặc `addSuppressed` | Một hoặc nhiều lỗi phụ bị **gác lại** để giữ exception chính |

Một exception có thể có cả `cause` và nhiều `suppressed`. Không tự suy luận rằng mỗi lỗi cleanup luôn là cause; trong `try-with-resources`, **lỗi cleanup đi vào suppressed** nếu đã có lỗi chính từ thân `try`.

## 8. Ví dụ chạy được: bảo toàn lỗi chính và lỗi cleanup

Lưu tệp **`SuppressedCleanupDemo.java`**:

```java
public class SuppressedCleanupDemo {
    static class Resource implements AutoCloseable {
        @Override
        public void close() {
            System.out.println("Đang đóng tài nguyên");
            throw new IllegalStateException("Đóng thất bại");
        }
    }

    public static void main(String[] args) {
        try (Resource resource = new Resource()) {
            System.out.println("Đang xử lý");
            throw new IllegalArgumentException("Dữ liệu sai");
        } catch (IllegalArgumentException e) {
            System.out.println("Lỗi chính: " + e.getMessage());
            System.out.println("Số lỗi suppressed: "
                    + e.getSuppressed().length);
            System.out.println("Lỗi phụ: "
                    + e.getSuppressed()[0].getMessage());
            System.out.println("Cause null: " + (e.getCause() == null));
        }
        System.out.println("Main tiếp tục");
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 SuppressedCleanupDemo.java
java SuppressedCleanupDemo
```

**Stdout chính xác** khi hiển thị UTF-8:

```text
Đang xử lý
Đang đóng tài nguyên
Lỗi chính: Dữ liệu sai
Số lỗi suppressed: 1
Lỗi phụ: Đóng thất bại
Cause null: true
Main tiếp tục
```

Ở đây, thân `try` ném `IllegalArgumentException` (A). Khi rời `try`, `close()` được gọi và ném `IllegalStateException` (B). Java giữ A làm exception chính, còn B nằm ở `A.getSuppressed()[0]`. Handler bắt A vẫn hoạt động; caller không bị chuyển bất ngờ sang xử lý B.

Kết quả `Cause null: true` cho thấy không có chuỗi `cause` nào được thiết lập; quan hệ giữa A và B được lưu trong **suppressed**, không phải `getCause()`.

Ví dụ giả định luôn có một suppressed exception để minh họa truy cập `[0]`; với mã thực, **kiểm tra độ dài trước khi truy cập** và không mặc định mọi exception đều có suppressed.

## 9. Nhiều tài nguyên: đóng ngược thứ tự và giữ tất cả lỗi đóng

Khi khai báo nhiều tài nguyên, mỗi resource đã khởi tạo thành công được đóng theo thứ tự từ phải sang trái. Nếu thân `try` đã ném exception chính, các exception phát sinh từ `close()` được thêm vào danh sách suppressed của exception chính.

Lưu **`MultipleCleanupDemo.java`**:

```java
public class MultipleCleanupDemo {
    static class Resource implements AutoCloseable {
        private final String name;

        Resource(String name) {
            this.name = name;
            System.out.println("Mở " + name);
        }

        @Override
        public void close() {
            System.out.println("Đóng " + name);
            throw new IllegalStateException("Lỗi đóng " + name);
        }
    }

    public static void main(String[] args) {
        try (Resource first = new Resource("A");
             Resource second = new Resource("B")) {
            System.out.println("Trong try");
            throw new IllegalArgumentException("Lỗi xử lý");
        } catch (IllegalArgumentException e) {
            System.out.println("Chính: " + e.getMessage());
            System.out.println("Suppressed: " + e.getSuppressed().length);
            for (Throwable t : e.getSuppressed()) {
                System.out.println("Phụ: " + t.getMessage());
            }
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 MultipleCleanupDemo.java
java MultipleCleanupDemo
```

**Stdout chính xác:**

```text
Mở A
Mở B
Trong try
Đóng B
Đóng A
Chính: Lỗi xử lý
Suppressed: 2
Phụ: Lỗi đóng B
Phụ: Lỗi đóng A
```

Resource B được đóng trước A, nên thứ tự suppressed cũng là lỗi đóng B trước rồi đến lỗi đóng A. **Không chỉ tài nguyên cuối mới được đóng**: Java vẫn cố đóng các tài nguyên còn lại đã được khởi tạo thành công, kể cả khi một thao tác đóng ném exception.

Đây là lợi thế lớn của `try-with-resources` so với kiểu cleanup thủ công không có chính sách rõ: các lỗi đóng không buộc chương trình đánh mất nguyên nhân chính hoặc bỏ qua những tài nguyên khác.

## 10. Khi cleanup là lỗi duy nhất, nó trở thành lỗi chính

`try-with-resources` không làm biến mất lỗi đóng. Nếu thân `try` hoàn tất bình thường nhưng `close()` thất bại, thì **lỗi cleanup là lỗi chính của toàn bộ câu lệnh**.

Lưu **`OnlyCleanupFailsDemo.java`**:

```java
public class OnlyCleanupFailsDemo {
    static class Resource implements AutoCloseable {
        @Override
        public void close() {
            System.out.println("Đang đóng");
            throw new IllegalStateException("Lỗi cleanup");
        }
    }

    public static void main(String[] args) {
        try (Resource resource = new Resource()) {
            System.out.println("Work thành công");
        } catch (IllegalStateException e) {
            System.out.println("Bắt: " + e.getMessage());
            System.out.println("Suppressed: " + e.getSuppressed().length);
        }
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 --release 17 OnlyCleanupFailsDemo.java
java OnlyCleanupFailsDemo
```

**Stdout chính xác:**

```text
Work thành công
Đang đóng
Bắt: Lỗi cleanup
Suppressed: 0
```

Thân `try` đã chạy hết nhưng **toàn bộ câu lệnh `try-with-resources` không hoàn tất bình thường** vì `close()` thất bại. B trở thành exception chính và không có lỗi chính trước đó để đính suppressed. Không nên báo thành công toàn bộ thao tác nếu hợp đồng yêu cầu đóng/flushing thành công trước khi xác nhận.

## 11. Lỗi khi khởi tạo tài nguyên cũng cần được bảo toàn

`try-with-resources` còn xử lý tình huống một tài nguyên đã mở thành công nhưng việc **khởi tạo tài nguyên tiếp theo** thất bại. Java sẽ cố đóng những tài nguyên đã mở, và nếu việc đóng phát sinh lỗi, lỗi đó có thể được đính kèm vào exception chính phát sinh khi khởi tạo.

Ví dụ độc lập **`InitializationCleanupDemo.java`**:

```java
public class InitializationCleanupDemo {
    static class Resource implements AutoCloseable {
        private final String name;

        Resource(String name) {
            this.name = name;
            System.out.println("Mở " + name);
            if ("B".equals(name)) {
                throw new IllegalArgumentException("Không tạo được B");
            }
        }

        @Override
        public void close() {
            System.out.println("Đóng " + name);
            throw new IllegalStateException("Không đóng được " + name);
        }
    }

    public static void main(String[] args) {
        try (Resource first = new Resource("A");
             Resource second = new Resource("B")) {
            System.out.println("Không tới thân try");
        } catch (IllegalArgumentException e) {
            System.out.println("Chính: " + e.getMessage());
            System.out.println("Phụ: "
                    + e.getSuppressed()[0].getMessage());
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 InitializationCleanupDemo.java
java InitializationCleanupDemo
```

**Stdout chính xác:**

```text
Mở A
Mở B
Đóng A
Chính: Không tạo được B
Phụ: Không đóng được A
```

Resource A đã khởi tạo thành công. Constructor của B ném ngoại lệ trước khi B trở thành resource đã được quản lý thành công, nên Java **không gọi `close()` cho B** trong cấu trúc này; A được đóng và lỗi đóng A được gắn suppressed vào lỗi khởi tạo B.

Đây là một lý do quan trọng để tránh tự viết chuỗi mở/đóng tài nguyên dài bằng `finally` thủ công: các đường thất bại giữa chừng rất dễ bỏ sót cleanup hoặc vô tình che exception đầu tiên.

## 12. Một ví dụ thực tế với file I/O

Đối tượng từ `Files.newBufferedReader` triển khai `AutoCloseable`, nên Java có thể quản lý việc đóng tài nguyên qua `try-with-resources`.

Ví dụ **phương thức minh họa** (chưa có `main`, và phụ thuộc nội dung tệp thật):

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

class ConfigReader {
    static String firstLine(Path path) throws IOException {
        try (BufferedReader reader = Files.newBufferedReader(path)) {
            return reader.readLine();
        }
    }
}
```

Cấu trúc này đảm bảo Java **cố gọi `reader.close()`** khi rời khối, kể cả khi `readLine()` ném `IOException`. Nếu cả đọc và đóng đều ném exception, lỗi đóng có thể nằm trong `getSuppressed()` của lỗi đọc chính.

Lệnh gọi cần chạy trong chương trình có đường dẫn hợp lệ; vì đầu ra phụ thuộc môi trường/tệp, ví dụ này **không công bố stdout cố định**. `readLine()` có thể trả `null` nếu đã hết dữ liệu, và điều đó không đồng nghĩa ngoại lệ.

Tránh mô hình “mở reader → gọi `readLine` → gọi `close` ở cuối hàm” mà không có cleanup cấu trúc: nếu `readLine` ném lỗi, dòng `close` bình thường ở cuối có thể bị bỏ qua.

## 13. Vì sao không tự động chuyển sang `getCause()`?

Nếu `finally` ném B khi A đang chờ, Java **không tự** làm `B.initCause(A)` hay `B.addSuppressed(A)`. Chỉ những đoạn code/hệ thống được thiết kế để liên kết ngoại lệ mới tạo mối liên hệ đó.

Có ba mô hình khác nhau:

| Mô hình | Caller thấy ngoại lệ chính nào? | Xem lỗi còn lại ở đâu? |
| --- | --- | --- |
| `try` ném A, `finally` ném B (không xử lý) | B | A có thể mất khỏi kết quả ném |
| `try` ném A, `catch` ném `new ServiceException("...", A)` | Exception wrapper mới | `getCause()` trả A |
| `try-with-resources`: thân ném A, `close` ném B | A | `getSuppressed()` của A chứa B |

Một ngoại lệ được bọc (*wrapping*) và một ngoại lệ bị đính kèm (*suppressed*) đều cung cấp thông tin chẩn đoán, nhưng quan hệ của chúng khác nhau. **Cause** mô tả chuỗi lý do dẫn đến lỗi cấp cao; **suppressed** thường lưu sự cố phụ xảy ra trong lúc đang xử lý lỗi chính.

Nếu dùng `Throwable.printStackTrace()`, Java thường hiển thị phần `Suppressed:` cho suppressed exception và phần `Caused by:` cho nguyên nhân. Không dựa vào văn bản hay số dòng cụ thể của stack trace như một hợp đồng ổn định; khi xử lý có cấu trúc, dùng `getCause()`, `getSuppressed()` và loại ngoại lệ thực.

## 14. Khi phải dùng `finally` thủ công: tự giữ ngoại lệ chính một cách có chủ đích

Không phải mọi tài nguyên cũ đều triển khai `AutoCloseable`. Khi buộc phải cleanup thủ công, cần chính sách **không ghi đè A bằng B**. Một lựa chọn là bắt lỗi cleanup rồi đính kèm nó vào exception chính đang được ném.

Ví dụ **chỉ minh họa trường hợp hai thao tác công bố `IOException`**:

```java
import java.io.IOException;

class LegacyCleanup {
    static void work() throws IOException {
        throw new IOException("Work failed");
    }

    static void cleanup() throws IOException {
        throw new IOException("Cleanup failed");
    }

    static void run() throws IOException {
        IOException primary = null;
        try {
            work();
        } catch (IOException e) {
            primary = e;
            throw e;
        } finally {
            try {
                cleanup();
            } catch (IOException closing) {
                if (primary != null) {
                    primary.addSuppressed(closing);
                } else {
                    throw closing;
                }
            }
        }
    }
}
```

Đây là **lớp minh họa không có `main`**. Khi `work()` ném `IOException`, handler giữ A trong biến `primary` và ném lại A. `finally` chạy `cleanup()`, nhận B và gắn B vào `primary`, rồi hoàn tất bình thường; do đó **A tiếp tục được truyền ra cùng suppressed B**.

Nếu `work()` hoàn tất bình thường, `primary == null`, và lỗi cleanup B sẽ được ném ra như lỗi chính. Cách tiếp cận này tránh mất lỗi gốc **trong phạm vi `IOException` đã thiết kế**. Nó **không** phải thư viện cleanup tổng quát cho mọi `RuntimeException` hoặc `Error`: nếu `work()` ném một loại khác mà handler không bắt, cleanup mới vẫn có thể che lỗi đó. Cũng cần xét điều kiện tài nguyên đã thực sự được mở và có cần cleanup hay không.

Do đó, **ưu tiên `try-with-resources` khi có thể**. Nếu thư viện cũ không triển khai `AutoCloseable`, cân nhắc bọc một adapter `AutoCloseable`, rồi dùng cấu trúc quản lý tài nguyên của Java thay vì viết lặp lại logic giữ primary/suppressed bằng tay.

## 15. Dùng adapter `AutoCloseable` cho API cũ

Giả sử một API cũ chỉ cung cấp phương thức `release()` mà không triển khai `AutoCloseable`. Có thể tạo adapter:

```java
class LegacySession {
    void doWork() {
        throw new IllegalArgumentException("Work failed");
    }

    void release() {
        throw new IllegalStateException("Release failed");
    }
}

class SessionAdapter implements AutoCloseable {
    private final LegacySession session;

    SessionAdapter(LegacySession session) {
        this.session = session;
    }

    void doWork() {
        session.doWork();
    }

    @Override
    public void close() {
        session.release();
    }
}
```

Đây là **hai lớp minh họa**. Khi dùng:

```java
try (SessionAdapter resource =
             new SessionAdapter(new LegacySession())) {
    resource.doWork();
}
```

là **đoạn code trong phương thức**, Java sẽ quản lý `close()` của adapter. Nếu `doWork` ném `IllegalArgumentException`, rồi `release` ném `IllegalStateException`, exception đầu vẫn là exception chính, và exception thứ hai được đính kèm suppressed. Adapter giúp đóng gói trách nhiệm cleanup ở một nơi.

Cần bảo đảm adapter thực sự sở hữu tài nguyên và không đóng sai một đối tượng dùng chung. Không nên tự động “adapter hóa” mọi dependency nếu người gọi không có quyền quản lý vòng đời của tài nguyên.

## 16. Kiểm thử masking và suppressed bằng kiểu, không bằng chuỗi stack trace

Một bài test tốt cần khẳng định **exception chính đúng loại và thông điệp**, cũng như **danh sách suppressed**. Không chỉ kiểm tra có lỗi xuất hiện trên console.

Ví dụ Java 17 độc lập **`SuppressedAssertionsDemo.java`** không yêu cầu thư viện test ngoài:

```java
public class SuppressedAssertionsDemo {
    static class Resource implements AutoCloseable {
        @Override
        public void close() {
            throw new IllegalStateException("cleanup");
        }
    }

    static void run() {
        try (Resource resource = new Resource()) {
            throw new IllegalArgumentException("work");
        }
    }

    public static void main(String[] args) {
        try {
            run();
            throw new AssertionError("Phải có exception");
        } catch (IllegalArgumentException e) {
            if (!"work".equals(e.getMessage())) {
                throw new AssertionError("Sai lỗi chính");
            }
            Throwable[] other = e.getSuppressed();
            if (other.length != 1
                    || !(other[0] instanceof IllegalStateException)
                    || !"cleanup".equals(other[0].getMessage())) {
                throw new AssertionError("Sai lỗi suppressed");
            }
            System.out.println("PASS: giữ lỗi chính và lỗi cleanup");
        }
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 --release 17 SuppressedAssertionsDemo.java
java SuppressedAssertionsDemo
```

**Stdout chính xác:**

```text
PASS: giữ lỗi chính và lỗi cleanup
```

Bài test này chủ động ném `AssertionError` khi kết quả trái mong đợi, không phụ thuộc việc JVM có bật tùy chọn `-ea` cho lệnh `assert` hay không. Khi exception xảy ra đúng như thiết kế, nhánh `catch` kiểm tra cấu trúc dữ liệu lỗi và in một thông báo duy nhất.

Trong bộ kiểm thử thực tế có thể dùng JUnit `assertThrows` và các assertion về `getSuppressed()`; logic cần kiểm tra vẫn là **primary exception đúng** và **cleanup exception không bị mất**.

## 17. Những sai lầm cần tránh

### 17.1. Bắt rồi nuốt sạch lỗi cleanup

```java
finally {
    try {
        cleanup();
    } catch (Exception ignored) {
        // Mất dấu vết cleanup failure.
    }
}
```

Đây là **khung minh họa**, chưa có `cleanup()`. Cách này có thể bảo toàn A đang lan truyền, nhưng **làm mất B**. Nếu lỗi cleanup quan trọng đối với tài nguyên, cần chiến lược ghi nhận phù hợp hoặc dùng suppressed; không đơn giản bỏ qua.

### 17.2. Cleanup trong `finally` tự ném exception mới

Nếu cleanup lỗi, `finally` có thể đẩy B lên và che A. Đây là vấn đề chính của bài; thay bằng `try-with-resources` nếu có tài nguyên `AutoCloseable`.

### 17.3. Dùng `return` trong `finally`

`return` trong `finally` có thể loại bỏ cả lỗi lẫn giá trị return đang chờ. Tránh dùng cho nghiệp vụ hoặc dọn dẹp.

### 17.4. Cho rằng `try-with-resources` luôn gắn suppressed

Nếu **chỉ `close()` ném lỗi**, lỗi đó là exception chính, không có exception chính trước đó để gắn suppressed. Nếu `close()` thành công, không có suppressed mới. Không truy `getSuppressed()[0]` khi chưa kiểm tra mảng có phần tử.

### 17.5. Đọc `getCause()` mà quên `getSuppressed()`

Một lỗi công việc chính có thể có cause riêng và **đồng thời** có suppressed cleanup exception. Chỉ lần theo `cause` có thể bỏ sót các vấn đề về tài nguyên.

### 17.6. Ghi log mọi tầng hoặc để lộ chi tiết

Chọn nơi có đủ ngữ cảnh để log cả exception chính, cause và suppressed. Tránh ghi thông tin nhạy cảm như mật khẩu, token hay nội dung nội bộ vào message, rồi hiển thị nguyên stack trace cho người dùng cuối.

### 17.7. Cho rằng lỗi đã được giải quyết chỉ vì handler bắt được

Một handler có thể bắt exception chính nhưng vẫn để tài nguyên ở trạng thái không nhất quán. **Bảo toàn dấu vết lỗi khác với khôi phục trạng thái ứng dụng**. Có thể cần rollback giao dịch, hủy yêu cầu, đóng các tài nguyên khác hoặc thông báo job thất bại.

### 17.8. Xem `finally` là bảo đảm tuyệt đối

`finally` thường chạy khi rời `try`/`catch` qua các đường đi Java bình thường và bất thường. Tuy nhiên tiến trình bị chấm dứt cưỡng bức, JVM gặp sự cố nghiêm trọng hoặc `System.exit` có thể ngăn cleanup. `try-with-resources` cũng không thể bảo đảm tài nguyên bên ngoài thực sự đóng thành công nếu `close()` đã thất bại.

## 18. Cách chẩn đoán một lỗi có cleanup failure

Khi một tác vụ thất bại, hãy đặt các câu hỏi theo thứ tự:

1. **Exception mà caller nhận được là gì?** Tên lớp, message, stack trace đầu tiên.
2. **Nó xuất hiện trong công việc chính hay trong cleanup?** Đọc các frame và cấu trúc `try/finally` hoặc `try-with-resources`.
3. **Có `getCause()` không?** Xác định chuỗi nguyên nhân khi exception được wrapping.
4. **Có `getSuppressed()` không?** Liệt kê và kiểm tra từng lỗi phụ, đặc biệt khi có nhiều tài nguyên.
5. **Có `return`, `throw` hoặc exception mới trong `finally` không?** Chúng có thể làm mất exception trước đó.
6. **Tài nguyên được khai báo/đóng theo thứ tự nào?** Với `try-with-resources`, đóng theo thứ tự ngược; khi khởi tạo thất bại, những tài nguyên đã mở được cố đóng.
7. **Có thể tạo lại lỗi mà không gây tác động nguy hiểm không?** Dùng fake resource như các ví dụ để test tình huống công việc + cleanup cùng thất bại.
8. **Chính sách ứng dụng là gì?** Khi thao tác chính thất bại, không báo thành công chỉ vì cleanup hoàn tất; khi cleanup thất bại, đánh giá ảnh hưởng tài nguyên trước khi tiếp tục.

Một phương pháp kiểm thử đáng tin là chủ động làm **cả hai đường thất bại**, rồi kiểm tra rằng caller nhận **A là primary, B là suppressed**. Điều này trực tiếp phát hiện lỗi masking mà các test chỉ kiểm tra “có ném exception” thường bỏ sót.

## 19. Câu hỏi tự kiểm tra

**1. Thân `try` ném A, `finally` hoàn tất bình thường. Caller nhận gì?**  
Caller nhận A (trừ khi một cấu trúc xử lý bao ngoài bắt hoặc chuyển đổi nó). `finally` không tự làm mất A nếu kết thúc bình thường.

**2. Thân `try` ném A, `finally` ném B. Caller nhận gì?**  
Theo cấu trúc `try/finally` thông thường, B trở thành exception thoát ra; A có thể bị che và không tự nằm trong `cause` hay `suppressed`.

**3. `catch` đã `throw e` với A, `finally` lại ném B. `throw e` có bảo đảm A đến caller không?**  
Không. B có thể thay thế A vì `finally` hoàn tất bất thường.

**4. `finally` có `return 1` trong khi `try` ném A thì sao?**  
`return` từ `finally` có thể che A và khiến phương thức trả về 1. Đây là phản ví dụ cần tránh.

**5. Trong `try-with-resources`, thân ném A và `close()` ném B thì lỗi nào là primary?**  
Thông thường A vẫn là primary; B được đính kèm suppressed. Có thể xem B qua `A.getSuppressed()`.

**6. Thân `try` thành công nhưng `close()` ném B thì sao?**  
B trở thành exception chính của câu lệnh `try-with-resources`, không phải suppressed của một exception không tồn tại.

**7. Hai tài nguyên A và B cùng được khai báo trong `try (A a = ...; B b = ...)`. Thứ tự đóng?**  
B trước A. Nếu cả hai `close()` lỗi khi thân đã ném exception, các lỗi đóng sẽ được ghi dưới dạng suppressed theo thứ tự xảy ra.

**8. `getCause()` và `getSuppressed()` giống nhau không?**  
Không. Cause diễn tả quan hệ nguyên nhân của exception wrapper; suppressed lưu các exception phụ được giữ lại, thường khi đóng tài nguyên.

**9. Nếu resource B ném lỗi ngay trong constructor còn A đã mở, A có được đóng không?**  
`try-with-resources` cố đóng A. Nếu việc đóng A cũng ném, lỗi đóng có thể bị suppressed vào lỗi khởi tạo B.

**10. Một lỗi cleanup được suppressed có nghĩa nó không cần xử lý nữa không?**  
Không. Suppressed chỉ giữ thông tin chẩn đoán và ưu tiên lỗi chính; cần xem xét trạng thái tài nguyên, rò rỉ, dữ liệu hoặc side effect.

## 20. Checklist thiết kế cleanup

Trước khi hoàn tất mã Java có xử lý tài nguyên:

- Tài nguyên có triển khai `AutoCloseable` không? Nếu có, ưu tiên `try-with-resources`.
- Có cả đường công việc chính thất bại **và** cleanup thất bại không? Đã test cả hai xảy ra cùng lúc chưa?
- Nếu dùng `finally`, liệu một lệnh `throw` hoặc `return` mới có thể che exception đang chờ không?
- Mã cleanup có phân biệt **lỗi chính** với **lỗi phụ** không?
- Caller có thể đọc `getSuppressed()` và `getCause()` để điều tra đầy đủ không?
- Với nhiều tài nguyên, thứ tự tạo/đóng và việc xử lý lỗi trong khởi tạo đã được kiểm tra chưa?
- Với checked exception, chữ ký `throws` có đúng hợp đồng không? Nếu close có thể ném checked exception, caller phải được xử lý/khai báo phù hợp.
- Việc đóng tài nguyên thất bại có ảnh hưởng tính nhất quán của dữ liệu hoặc xác nhận thành công không?
- Có chỗ nào đang `catch (Exception ignored)` và bỏ qua một lỗi cần được ghi nhận không?
- Log có đủ ngữ cảnh nhưng không lộ dữ liệu nhạy cảm và không bị lặp vô ích ở mọi tầng không?

## 21. Ghi nhớ cuối cùng

**Ngoại lệ cleanup che mất ngoại lệ ban đầu khi đoạn dọn dẹp (thường trong `finally`) hoàn tất bất thường và thay thế lý do thất bại đang được truyền ra.** Điều này có thể khiến caller nhận một lỗi đóng tài nguyên thay vì lỗi nghiệp vụ/kỹ thuật ban đầu. `return` trong `finally` còn có thể xóa luôn tín hiệu exception.

**`try-with-resources` là cách ưu tiên cho tài nguyên `AutoCloseable`**: nếu công việc chính ném A và đóng ném B, Java giữ A là primary và gắn B trong `getSuppressed()`; nếu chỉ đóng thất bại, B là lỗi chính. Đừng nhầm suppressed với cause, và đừng nghĩ việc lưu hai lỗi tự động phục hồi hệ thống.

Nguyên tắc áp dụng: **bảo toàn nguyên nhân đầu tiên có ý nghĩa, không để cleanup vô tình ghi đè nó, vẫn ghi nhận các lỗi dọn dẹp, và bảo đảm caller hiểu rõ thao tác đã thành công hay thất bại.**
