# Ném lại cùng đối tượng ngoại lệ bằng `throw e` trong Java

Trong Java, khi một ngoại lệ đã được bắt bằng `catch`, lập trình viên có thể **ném lại chính đối tượng ngoại lệ đó** bằng lệnh `throw e;`. Cách làm này gọi là **rethrow** (ném lại). Nó hữu ích khi tầng hiện tại cần thực hiện một công việc giới hạn, chẳng hạn ghi nhận ngữ cảnh, giải phóng tài nguyên hoặc cập nhật trạng thái, nhưng **không có quyền hay khả năng xử lý hoàn toàn lỗi**, nên cần để tầng gọi cao hơn tiếp tục quyết định.

Điểm quyết định là: **`throw e` ném lại đối tượng đang được tham chiếu bởi `e`; nó không tự tạo một exception mới.** Vì vậy đối tượng, loại runtime, message, cause và thông tin stack trace đang có được giữ lại, trừ khi chính mã đã sửa đổi những dữ liệu có thể thay đổi đó. Sau khi lệnh `throw e` chạy, `catch` hiện tại cũng kết thúc bất thường; Java tiếp tục tìm trình xử lý phù hợp ở phạm vi bên ngoài.

Bài này tập trung vào chính lệnh `throw e`: vì sao cần rethrow, đối tượng nào được ném, luồng chạy đi đâu, checked/unchecked exception có ảnh hưởng thế nào, đặc điểm stack trace, quy tắc *precise rethrow* và những sai lầm dễ khiến lỗi gốc bị che mất.

## 1. Cú pháp `throw e` và điều kiện để dùng

Xét đoạn mã:

```java
try {
    riskyOperation();
} catch (IllegalStateException e) {
    System.out.println("Đã ghi nhận lỗi: " + e.getMessage());
    throw e;
}
```

Đây là **đoạn minh họa nằm trong một phương thức**, giả sử `riskyOperation()` đã được định nghĩa. Ý nghĩa:

1. `riskyOperation()` phát sinh một ngoại lệ kiểu `IllegalStateException` hoặc lớp con.
2. `catch` nhận **tham chiếu** đến đối tượng ngoại lệ đó qua biến `e`.
3. Câu lệnh in trong `catch` thực hiện công việc ở tầng hiện tại.
4. `throw e;` ném lại đối tượng mà `e` đang trỏ tới.
5. Java bỏ phần còn lại của handler (nếu có) và lan truyền exception tới phạm vi ngoài. `finally` hoặc đóng tài nguyên liên quan vẫn được thực hiện theo quy tắc.

Cú pháp tổng quát của lệnh `throw` là `throw <expression>;`, trong đó biểu thức phải có kiểu tham chiếu phù hợp với `Throwable` theo quy tắc của Java. `e` thường là tham số của `catch`, nhưng cũng có thể là một biến kiểu exception trong phạm vi khác.

**Phân biệt `throw` và `throws`:**

- `throw e;` là **câu lệnh tại runtime**, thực sự phát sinh việc ném đối tượng.
- `throws IOException` là **khai báo trong chữ ký phương thức**, chỉ ra khả năng phương thức lan truyền một checked exception; bản thân nó không ném đối tượng.
- `try/catch` quyết định có một handler tại chỗ hay không; `throw e` trong handler có nghĩa tầng đó quyết định **không hoàn tất xử lý tại đây**.

Đối với checked exception, trình biên dịch sẽ kiểm tra nghĩa vụ `catch-or-declare` đối với đường đi ném lại. Đối với `RuntimeException` hoặc `Error`, chữ ký `throws` không bắt buộc chỉ vì có `throw e`.

## 2. Vì sao đã bắt exception rồi vẫn ném lại?

Bắt được một exception **không đồng nghĩa** với xử lý xong hậu quả của nó. Một tầng thấp có thể biết chuyện gì vừa xảy ra nhưng không biết nên dừng một request, báo người dùng, chọn tệp khác hay hủy quy trình.

Ví dụ một phương thức nạp cấu hình thất bại vì `IOException`:

- Tầng thao tác tệp biết đường dẫn nào không đọc được.
- Tầng dịch vụ có thể biết chức năng nào đang chờ cấu hình.
- Tầng khởi động ứng dụng có thể quyết định dừng khởi động hoặc thử cấu hình dự phòng.

Nếu tầng dịch vụ chỉ muốn ghi một dấu vết chẩn đoán rồi **giữ nguyên hợp đồng exception**, ném lại chính `IOException` là lựa chọn rõ ràng. Tầng cao hơn sẽ nhận được cùng đối tượng ngoại lệ, thay vì nhận một giá trị “thành công” giả.

Các mục đích hợp lý thường gặp:

| Lý do | Công việc trước `throw e` | Vì sao cần ném tiếp |
| --- | --- | --- |
| Thêm dấu vết chẩn đoán | Ghi ngữ cảnh request hoặc tên thao tác, bảo vệ dữ liệu nhạy cảm | Tầng hiện tại không quyết định được phục hồi |
| Cleanup hoặc cập nhật trạng thái | Hủy công việc cục bộ, đánh dấu một bước thất bại | Caller còn cần biết thao tác tổng thể đã lỗi |
| Giữ nguyên hợp đồng API | Không thay đổi loại exception, message, cause | Caller đã có handler dành cho loại gốc |
| Tập trung chính sách lỗi ở tầng cao | Tầng dưới không sinh phản hồi HTTP/UI | Tầng ranh giới quyết định phản hồi cuối |
| Bảo toàn tín hiệu thất bại | Không trả `null`, `false` hay dữ liệu thay thế không được phép | Tránh khiến caller hiểu lầm thao tác đã hoàn thành |

Không cần viết `catch` chỉ để có `throw e` nếu tầng hiện tại không thực hiện điều gì có ích. Khi không cần xử lý, có thể để ngoại lệ lan truyền tự nhiên; cách đó thường ngắn gọn và giữ nguyên tín hiệu lỗi.

## 3. `throw e` giữ nguyên identity của đối tượng

Java so sánh hai tham chiếu bằng `==` để xác định liệu chúng có trỏ tới **cùng một đối tượng** hay không. Lệnh `throw e` không tạo instance mới, nên tầng bắt bên ngoài nhận đúng instance mà tầng trong đã ném.

Lưu chương trình sau thành **`RethrowIdentityDemo.java`**:

```java
public class RethrowIdentityDemo {
    private static IllegalArgumentException original;

    static void lowLevel() {
        original = new IllegalArgumentException("Mã đầu vào sai");
        throw original;
    }

    static void middleLevel() {
        try {
            lowLevel();
        } catch (IllegalArgumentException e) {
            System.out.println("Giữa: cùng đối tượng = " + (e == original));
            throw e;
        }
    }

    public static void main(String[] args) {
        try {
            middleLevel();
        } catch (IllegalArgumentException e) {
            System.out.println("Ngoài: cùng đối tượng = " + (e == original));
            System.out.println("Loại: " + e.getClass().getSimpleName());
            System.out.println("Message: " + e.getMessage());
        }
        System.out.println("Đã xử lý ở main");
    }
}
```

Biên dịch và chạy bằng Java 17 trở lên:

```bash
javac -encoding UTF-8 --release 17 RethrowIdentityDemo.java
java RethrowIdentityDemo
```

**Stdout chính xác**, với môi trường hiển thị UTF-8:

```text
Giữa: cùng đối tượng = true
Ngoài: cùng đối tượng = true
Loại: IllegalArgumentException
Message: Mã đầu vào sai
Đã xử lý ở main
```

Cả hai biểu thức `e == original` đều là `true`. `middleLevel()` chỉ ném lại đúng tham chiếu nhận được. Đối tượng gốc không bị đổi thành `RuntimeException` hay đối tượng khác.

Biến `original` ở ví dụ chỉ phục vụ kiểm chứng identity; ứng dụng thực không nên lưu exception mới nhất trong trường `static` toàn cục để truyền lỗi giữa các luồng, vì có thể gây tranh chấp và giữ tham chiếu không cần thiết. Kênh truyền lỗi thực sự ở đây là `throw`/ `catch`.

Cũng cần phân biệt: cùng đối tượng **không có nghĩa** toàn bộ thuộc tính bất biến. Một chương trình có thể gọi `setStackTrace(...)`, `fillInStackTrace()` hoặc một số API trên `Throwable` để thay đổi dữ liệu chẩn đoán; nhưng bản thân lệnh `throw e` không tự thực hiện những sửa đổi đó.

## 4. `throw e` thay đổi luồng thực thi như thế nào?

Một exception khi được ném lại phải tiếp tục đi tới **handler bên ngoài** tương thích, hoặc xa hơn trên call stack. Java không thử các nhánh `catch` còn lại của **cùng câu lệnh `try`** như thể chúng là handler của exception vừa phát sinh trong `catch` đầu tiên.

Khung đơn giản:

```text
caller
  └─ service
       └─ try { repository.read(); }
          catch (IOException e) {
              ghi nhận lỗi
              throw e   ───────────┐
          }                      │
  ◀──────────────────────────────┘
  catch (IOException e) { xử lý tại caller }
  tiếp tục sau try/catch của caller
```

Lưu ý những hậu quả:

- Câu lệnh ngay sau `throw e;` theo đường thực thi đó không chạy; nếu đứng trực tiếp sau nó mà không có nhánh điều kiện, Java có thể báo lỗi **unreachable statement** khi biên dịch.
- Mã ở cuối `try` đã bị exception làm gián đoạn cũng không tự được chạy bù.
- Phương thức ném lại exception **thoát bất thường**; caller không thực hiện những lệnh đứng sau lời gọi nằm trong nhánh `try` đã bị ngắt.
- `finally` và các hoạt động dọn dẹp liên quan được xử lý khi rời phạm vi, theo quy tắc Java; nếu chính chúng ném exception mới, tín hiệu cuối cùng có thể thay đổi.
- Khi handler ở tầng ngoài xử lý xong **bình thường**, Java mới tiếp tục từ điểm sau cấu trúc `try/catch` của tầng đó, chứ không nhảy trở lại lời gọi ban đầu.

### Ví dụ có `finally` và vị trí tiếp tục

Lưu thành **`RethrowFlowDemo.java`**:

```java
public class RethrowFlowDemo {
    static void load() {
        throw new IllegalStateException("Không tải được");
    }

    static void process() {
        try {
            System.out.println("1. Trong try");
            load();
            System.out.println("2. Sau load");
        } catch (IllegalStateException e) {
            System.out.println("3. Catch trong");
            throw e;
        } finally {
            System.out.println("4. Finally trong");
        }
    }

    public static void main(String[] args) {
        try {
            process();
            System.out.println("5. Sau process");
        } catch (IllegalStateException e) {
            System.out.println("6. Catch ngoài: " + e.getMessage());
        }
        System.out.println("7. Sau catch ngoài");
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 --release 17 RethrowFlowDemo.java
java RethrowFlowDemo
```

**Stdout chính xác:**

```text
1. Trong try
3. Catch trong
4. Finally trong
6. Catch ngoài: Không tải được
7. Sau catch ngoài
```

Lệnh “2. Sau load” không chạy vì `load()` ném exception; “5. Sau process” không chạy vì `process()` đã thoát bất thường. `finally` vẫn thực hiện trước khi exception tới `catch` bên ngoài. Cuối cùng, `main` tiếp tục với lệnh số 7.

Đây chính là khác biệt giữa **ghi nhận ở một tầng rồi ném tiếp** và **giải quyết hoàn toàn tại tầng đó**. Nếu `catch` trong `process()` không `throw e` và kết thúc bình thường, lời gọi `process()` có thể trả về bình thường; lúc ấy câu lệnh số 5 có thể chạy, dù công việc `load()` không thành công. Có nên tiếp tục hay không tùy hợp đồng và trạng thái hệ thống.

## 5. Stack trace khi ném lại cùng exception

Một đối tượng `Throwable` thường thu nhận stack trace tại lúc khởi tạo (hoặc khi `fillInStackTrace()` được gọi), nếu cơ chế ghi stack trace được bật cho đối tượng đó. **`throw e` thông thường không tự khởi tạo stack trace mới**. Do đó, tầng ngoài vẫn nhìn thấy dấu vết gắn với exception ban đầu; lệnh `throw e` không được tự thêm làm điểm bắt đầu mới chỉ vì nó ném lại.

Hãy xem một ví dụ xác định đầu stack trace bằng tên phương thức thay vì in số dòng (vì số dòng có thể thay đổi khi sửa mã). Lưu thành **`RethrowTraceDemo.java`**:

```java
public class RethrowTraceDemo {
    static void source() {
        throw new IllegalArgumentException("Nguồn phát sinh");
    }

    static void relay() {
        try {
            source();
        } catch (IllegalArgumentException e) {
            System.out.println("Trong relay: "
                    + e.getStackTrace()[0].getMethodName());
            throw e;
        }
    }

    public static void main(String[] args) {
        try {
            relay();
        } catch (IllegalArgumentException e) {
            System.out.println("Trong main: "
                    + e.getStackTrace()[0].getMethodName());
            System.out.println("Số cause: " + (e.getCause() == null ? 0 : 1));
        }
    }
}
```

Lệnh:

```bash
javac --release 17 RethrowTraceDemo.java
java RethrowTraceDemo
```

**Stdout chính xác** trên Java 17 thông thường:

```text
Trong relay: source
Trong main: source
Số cause: 0
```

Ví dụ cho thấy phần tử đầu của stack trace vẫn chỉ `source` ở cả hai nơi. `relay` đã ném lại bằng `throw e`, nhưng không tự thay đổi dấu vết tại nguồn.

**Lưu ý quan trọng:** không nên phụ thuộc vào định dạng chuỗi `printStackTrace()`, số dòng hoặc nội dung stack trace cụ thể như hợp đồng ổn định giữa các phiên bản và chế độ thực thi JVM. Ngoài ra, `Throwable` cho phép sửa stack trace bằng API, có constructor vô hiệu hóa writable stack trace, và JVM có thể tối ưu một số exception tự phát sinh trong điều kiện đặc biệt. Tính chất chính cần nhớ là **không tạo exception mới** và **không tự gọi `fillInStackTrace()`** chỉ vì `throw e`.

### So sánh với `throw new ...`

Ba cách thường bị nhầm:

| Mã | Đối tượng được ném | Loại nhìn thấy ở caller | Thông tin lỗi gốc |
| --- | --- | --- | --- |
| `throw e;` | **Chính đối tượng `e`** | Loại runtime thực của `e` | Giữ như đang có |
| `throw new IllegalStateException("...", e);` | **Đối tượng mới** | `IllegalStateException` mới | `e` được giữ ở `cause` |
| `throw new IllegalStateException(e.getMessage());` | **Đối tượng mới** | `IllegalStateException` mới | Không giữ `e` ở `cause` nếu không truyền riêng |

`throw e` hợp lý khi caller cần nhận đúng loại và đối tượng ban đầu. **Wrapping** (`throw new SomeException(message, e)`) hợp lý khi tầng hiện tại cần đổi mức trừu tượng hoặc thêm ngữ cảnh vào hợp đồng mới. Nhưng wrapping không còn bảo toàn identity với exception gốc, và caller sẽ thấy stack trace của exception mới, trong khi exception cũ có thể truy ra qua `getCause()`.

Một số tình huống cần giữ nguyên loại checked exception để caller xử lý; lúc đó `throw e` có thể phù hợp hơn wrapping không có chủ đích.

## 6. Ví dụ đối chiếu rethrow với wrapping

Chương trình sau chạy được bằng Java 17+, lưu thành **`RethrowVsWrapDemo.java`**:

```java
public class RethrowVsWrapDemo {
    static IllegalArgumentException createProblem() {
        return new IllegalArgumentException("Giá trị âm");
    }

    static void rethrow(IllegalArgumentException problem) {
        try {
            throw problem;
        } catch (IllegalArgumentException e) {
            throw e;
        }
    }

    static void wrap(IllegalArgumentException problem) {
        try {
            throw problem;
        } catch (IllegalArgumentException e) {
            throw new IllegalStateException("Không hoàn tất yêu cầu", e);
        }
    }

    public static void main(String[] args) {
        IllegalArgumentException original = createProblem();

        try {
            rethrow(original);
        } catch (IllegalArgumentException e) {
            System.out.println("Rethrow same: " + (e == original));
            System.out.println("Rethrow cause: " + (e.getCause() == null));
        }

        try {
            wrap(original);
        } catch (IllegalStateException e) {
            System.out.println("Wrap same: " + (e == (Object) original));
            System.out.println("Wrap cause same: " + (e.getCause() == original));
            System.out.println("Wrap type: " + e.getClass().getSimpleName());
        }
    }
}
```

Chạy:

```bash
javac --release 17 RethrowVsWrapDemo.java
java RethrowVsWrapDemo
```

**Stdout chính xác:**

```text
Rethrow same: true
Rethrow cause: true
Wrap same: false
Wrap cause same: true
Wrap type: IllegalStateException
```

Ở phần rethrow, exception đúng là `original`, và `getCause()` vẫn `null`, vì mã không thiết lập cause. Ở phần wrapping, caller bắt một `IllegalStateException` mới; `getCause()` của nó trỏ về `original`, nên có thể lần theo chuỗi nguyên nhân.

Phép so sánh `e == (Object) original` ở ví dụ được ép về `Object` vì `e` có kiểu `IllegalStateException` và `original` có kiểu `IllegalArgumentException`, hai lớp anh em trong nhánh `RuntimeException`; ép về `Object` cho phép so sánh identity minh họa. Kết quả vẫn `false` vì đối tượng wrapper được tạo mới.

Đây là lý do `throw e` và `throw new ...` **khác nhau về hợp đồng, kiểu và dấu vết chẩn đoán**, dù cả hai đều khiến luồng thực thi hiện tại kết thúc bất thường.

## 7. Ném lại checked exception: `throws` vẫn phải phù hợp

Với checked exception, `throw e` vẫn là một đường có thể phát sinh checked exception tại thời điểm biên dịch. Nếu handler bắt `IOException` rồi ném lại, phương thức chứa nó phải **bắt tiếp bên trong một cấu trúc khác phù hợp hoặc khai báo `throws IOException` (hay kiểu cha được phép)**.

Lưu thành **`CheckedRethrowDemo.java`**:

```java
import java.io.IOException;

public class CheckedRethrowDemo {
    static void readConfig() throws IOException {
        throw new IOException("Không đọc được cấu hình");
    }

    static void loadService() throws IOException {
        try {
            readConfig();
            System.out.println("Đã đọc cấu hình");
        } catch (IOException e) {
            System.out.println("Dịch vụ ghi nhận: " + e.getMessage());
            throw e;
        }
    }

    public static void main(String[] args) {
        try {
            loadService();
        } catch (IOException e) {
            System.out.println("Main xử lý: " + e.getMessage());
        }
        System.out.println("Main vẫn hoạt động");
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 --release 17 CheckedRethrowDemo.java
java CheckedRethrowDemo
```

**Stdout chính xác:**

```text
Dịch vụ ghi nhận: Không đọc được cấu hình
Main xử lý: Không đọc được cấu hình
Main vẫn hoạt động
```

`IOException` là checked exception. Ở `loadService()`, dù đã viết `catch (IOException e)`, việc ném lại khiến phương thức vẫn có khả năng trả lỗi `IOException` ra ngoài, nên chữ ký khai báo `throws IOException`. `main()` xử lý lỗi ở nơi cao hơn.

Nếu bỏ `throws IOException` khỏi `loadService()` mà vẫn giữ `throw e`, mã sẽ gặp lỗi biên dịch vì checked exception chưa được xử lý/khai báo. Ngược lại, nếu handler bắt và xử lý hoàn toàn mà không ném tiếp, tùy phần mã còn lại, khai báo `throws` có thể không cần thiết.

Với unchecked exception như `IllegalStateException`, không có nghĩa vụ khai báo tương tự, kể cả khi được ném lại nhiều tầng.

## 8. Tính năng *precise rethrow* từ Java 7

Một điểm ít hiển nhiên: Java có cơ chế **phân tích chính xác các loại checked exception được ném lại** khi tham số `catch` là **final hoặc effectively final**. Điều này thường được gọi là *more precise rethrow analysis*.

Trước hết xét ví dụ Java 17 hợp lệ, lưu thành **`PreciseRethrowDemo.java`**:

```java
import java.io.IOException;

public class PreciseRethrowDemo {
    static void read() throws IOException {
        throw new IOException("Hỏng tệp");
    }

    // Dù catch kiểu Exception, Java nhận biết ở đây
    // checked exception có thể thoát ra là IOException.
    static void relay() throws IOException {
        try {
            read();
        } catch (Exception e) {
            System.out.println("Relay: " + e.getClass().getSimpleName());
            throw e;
        }
    }

    public static void main(String[] args) {
        try {
            relay();
        } catch (IOException e) {
            System.out.println("Main: " + e.getMessage());
        }
    }
}
```

Chạy:

```bash
javac --release 17 PreciseRethrowDemo.java
java PreciseRethrowDemo
```

**Stdout chính xác:**

```text
Relay: IOException
Main: Hỏng tệp
```

Tại sao `relay()` chỉ khai báo `throws IOException`, thay vì `throws Exception`? Vì trình biên dịch phân tích những exception có thể phát sinh từ thân `try`. Trong ví dụ, checked exception liên quan là `IOException`. Biến `e` không được gán lại nên đáp ứng điều kiện precise rethrow; phần unchecked exception nếu có không phải khai báo. Java không buộc chữ ký phải mở rộng thành `throws Exception` chỉ vì khai báo `catch (Exception e)`.

Điều kiện quan trọng:

1. `e` là tham số của `catch` được ném lại trong handler.
2. `e` là `final` hoặc **effectively final**: không bị gán lại ở thân `catch`.
3. Compiler xác định các loại exception có thể phát sinh từ khối `try` mà handler này có khả năng bắt, rồi áp dụng quy tắc precise rethrow theo ngôn ngữ.

Nếu gán lại tham số `e`, quy tắc precise rethrow thu hẹp kiểu không còn áp dụng như trước; `throw e` có thể bị xét theo kiểu khai báo rộng hơn của tham số. Vì vậy đoạn sau **cố ý không biên dịch** khi phương thức chỉ khai báo `throws IOException`:

```java
// Phản ví dụ cú pháp trong lớp có import java.io.IOException:
static void changedCatchVariable() throws IOException {
    try {
        throw new IOException("Lỗi A");
    } catch (Exception e) {
        e = new IOException("Lỗi B"); // e bị gán lại
        throw e; // Có thể bị yêu cầu xử lý/khai báo kiểu Exception
    }
}
```

Để giữ nguyên đối tượng lỗi gốc và tận dụng precise rethrow, **không gán lại tham số `catch`**. Thường cũng không có lý do hợp lý để đổi `e` thành một instance mới rồi gọi đó là “ném lại cùng đối tượng”.

### Multi-catch và tham số ngầm định final

Java cho phép bắt nhiều loại exception độc lập trong một `catch` bằng `|`. Tham số của multi-catch là **implicitly final**, không thể gán lại.

```java
import java.io.IOException;

class MultiCatchExample {
    static void run(boolean ioFailure) throws IOException {
        try {
            if (ioFailure) {
                throw new IOException("I/O");
            }
            throw new IllegalArgumentException("Tham số");
        } catch (IOException | IllegalArgumentException e) {
            throw e;
        }
    }
}
```

Đây là lớp minh họa **không có `main`**. `run` khai báo `IOException` vì đó là checked exception, còn `IllegalArgumentException` là unchecked và không đòi hỏi khai báo. Một `catch` multi-catch vẫn chỉ nhận đúng **một đối tượng** tại runtime; `throw e` ném lại đối tượng đó.

Không thể dùng multi-catch với hai loại mà một loại là lớp con của loại còn lại (ví dụ `IOException | Exception`) vì nhánh kiểu chồng lắp không hợp lệ.

## 9. Không được nhầm ném lại với thử lại thao tác

Hai từ tiếng Anh *rethrow* và *retry* tương tự nhau nhưng ý nghĩa hoàn toàn khác:

- **Rethrow**: ném lại **tín hiệu ngoại lệ** để tầng khác xử lý. Lệnh gây lỗi trước đó không tự chạy lại.
- **Retry**: chủ động **thực hiện lại thao tác** (gọi lại method, lặp hoặc gửi lại yêu cầu), thường sau khi kiểm tra lỗi có tính tạm thời.

Ví dụ:

```java
try {
    saveOrder();
} catch (IllegalStateException e) {
    recordFailure(e);
    throw e; // Không gọi lại saveOrder()
}
```

Đây là khung minh họa. Nếu `saveOrder()` đã viết dữ liệu rồi thất bại lúc trả kết quả, việc retry thiếu kiểm soát có thể tạo dữ liệu trùng. `throw e` chỉ chuyển lỗi đi, không lặp giao dịch.

Khi cần retry thật sự, phải xác định loại lỗi có thể phục hồi, số lần retry, timeout/backoff, khả năng idempotent của thao tác và side effect đã hoàn thành. Dùng `throw e` ở điểm hết khả năng xử lý nếu vẫn không thành công, chứ không nhầm nó là cơ chế retry.

## 10. `throw e` trong `catch` có tương tác thế nào với `finally`?

Một `finally` gắn với `try` thường thực hiện khi rời `try/catch`, kể cả khi `catch` ném lại exception:

```java
try {
    operation();
} catch (RuntimeException e) {
    auditFailure(e);
    throw e;
} finally {
    releaseLocalState();
}
```

Đây là mã minh họa; các phương thức phụ trợ cần được định nghĩa để chạy. Khi `throw e` xảy ra, `releaseLocalState()` được gọi trong quá trình rời cấu trúc, và sau đó exception tiếp tục lan truyền **nếu `finally` hoàn tất bình thường**.

Hai cảnh báo thiết yếu:

- Nếu `finally` ném exception mới, lỗi mới có thể trở thành exception thoát ra, **che khuất lỗi gốc** đang được ném lại.
- Nếu `finally` thực hiện `return`, nó có thể ghi đè việc ném exception, làm caller không còn thấy lỗi ban đầu.

Vì vậy hạn chế đặt `return` hoặc `throw` không chủ đích trong `finally`. Khi xử lý tài nguyên `AutoCloseable`, ưu tiên `try-with-resources` để có thứ tự đóng rõ ràng và giữ được suppressed exception khi cả thân `try` lẫn `close()` cùng thất bại.

## 11. Rethrow kết hợp với `try-with-resources`

Đối với tài nguyên `AutoCloseable`, rethrow không miễn trách nhiệm cleanup. Khi rời khối `try-with-resources`, các tài nguyên khởi tạo thành công được đóng theo **thứ tự ngược**. Tùy vị trí `catch`, tài nguyên có thể đã được đóng trước khi handler nhận lỗi.

Lưu chương trình Java 17+ thành **`RethrowResourceDemo.java`**:

```java
public class RethrowResourceDemo {
    static class Resource implements AutoCloseable {
        @Override
        public void close() {
            System.out.println("Đóng tài nguyên");
        }
    }

    static void work() {
        try (Resource resource = new Resource()) {
            throw new IllegalArgumentException("Dữ liệu lỗi");
        } catch (IllegalArgumentException e) {
            System.out.println("Ghi nhận trong work");
            throw e;
        }
    }

    public static void main(String[] args) {
        try {
            work();
        } catch (IllegalArgumentException e) {
            System.out.println("Main: " + e.getMessage());
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 --release 17 RethrowResourceDemo.java
java RethrowResourceDemo
```

**Stdout chính xác:**

```text
Đóng tài nguyên
Ghi nhận trong work
Main: Dữ liệu lỗi
```

Tài nguyên được đóng **trước** khi thực hiện `catch` trực tiếp gắn với `try-with-resources`. Sau đó `throw e` chuyển tiếp đúng exception ban đầu lên `main`.

Nếu `close()` cũng ném exception trong lúc thân `try` đã ném một exception khác, lỗi đóng thường được lưu trong `e.getSuppressed()` của exception chính. Lệnh `throw e` giữ nguyên đối tượng chính (cùng danh sách suppressed đang có), nên tầng ngoài có thể kiểm tra cả lỗi chính lẫn lỗi đóng. Nếu muốn hỗ trợ chẩn đoán toàn diện, không bỏ qua suppressed exceptions một cách máy móc.

## 12. Những sai lầm thường gặp khi dùng `throw e`

### 12.1. Viết `catch` chỉ để ném lại

```java
try {
    process();
} catch (Exception e) {
    throw e;
}
```

Đây là khung minh họa, với yêu cầu `throws` phù hợp nếu có checked exception. Nếu handler không ghi nhận ngữ cảnh, không dọn dẹp riêng và không chuyển đổi hợp đồng, khối `catch` thường không tạo giá trị mới. Có thể để exception lan tự nhiên; cleanup đặt trong `try-with-resources` hoặc `finally` khi thực sự cần.

### 12.2. Ghi log trùng ở từng tầng

```text
Repository: ghi đầy đủ stack trace rồi throw e
Service: ghi đầy đủ stack trace rồi throw e
Controller: ghi đầy đủ stack trace rồi trả lỗi
```

Một lỗi có thể thành ba bản ghi dài, khó theo dõi và tốn chi phí vận hành. Chọn nơi ghi log có đủ ngữ cảnh, dùng correlation/request ID khi phù hợp, và cân nhắc tránh log trùng. Rethrow giữ nguyên exception, nhưng **không buộc** mọi tầng phải ghi log.

### 12.3. Gọi `throw new ...` rồi tưởng vẫn là cùng đối tượng

`throw new RuntimeException(e)` tạo **wrapper mới** với `e` làm cause. Nó không tương đương `throw e`. Nếu mục tiêu chỉ là lan truyền nguyên trạng, sử dụng `throw e`.

### 12.4. Gán lại `e` rồi ném

```java
// Ý tưởng sai nếu mục tiêu là giữ đúng exception ban đầu:
catch (IllegalArgumentException e) {
    e = new IllegalArgumentException("Thông điệp khác");
    throw e;
}
```

Đây là phần minh họa trong `try/catch`, không phải chương trình độc lập. Handler trên ném một đối tượng **mới**, đã mất identity của lỗi ban đầu và không tự giữ cause/stack trace cũ. Với checked exception, việc gán lại biến `catch` cũng có thể làm mất cơ chế precise rethrow.

### 12.5. Làm mất nguyên nhân ở tầng bọc lỗi

Nếu cần đổi loại exception, phải chủ động giữ nguyên nhân:

```java
// Không giữ nguyên nhân:
throw new IllegalStateException("Không thể lưu đơn hàng");

// Giữ nguyên nhân (giả sử e đang là exception gốc):
throw new IllegalStateException("Không thể lưu đơn hàng", e);
```

Đây là hai lựa chọn **minh họa độc lập**, không đặt liên tiếp trong một khối thực thi. Cách thứ hai tạo wrapper mới nhưng giữ `e` trong `cause`. Khi chỉ cần lan truyền nguyên bản, `throw e` vẫn là cách giữ thông tin trực tiếp nhất.

### 12.6. Bắt sai loại hoặc nuốt cả `Error`

Không dùng `catch (Throwable e)` rồi `throw e` chỉ để “bắt mọi thứ” khi không có lý do kiến trúc rõ ràng. `Throwable` bao gồm cả `Error`, một số loại như `OutOfMemoryError` có thể khiến hệ thống ở trạng thái không phù hợp để tiếp tục công việc. Nếu bắt rộng tại một ranh giới giám sát đặc biệt, xử lý và chuyển tiếp phải đúng hợp đồng; mã nghiệp vụ thông thường nên chọn loại cụ thể.

### 12.7. Hiểu sai stack trace

`throw e` không tự tạo stack trace ở vị trí rethrow. Vì vậy nếu log chỉ dựa vào dòng đầu của stack trace để tìm “điểm rethrow”, có thể bỏ sót nơi tầng trung gian quyết định chuyển lỗi. Khi cần biết thêm ngữ cảnh, có thể ghi log ở đúng ranh giới hoặc wrapping có cause theo hợp đồng. Không gọi `fillInStackTrace()` chỉ để giả vờ lỗi gốc phát sinh ở một nơi khác.

### 12.8. Dùng rethrow để xử lý mọi kết quả nghiệp vụ

Một đơn hàng hết hàng, mã giảm giá hết hạn hoặc tìm kiếm không có kết quả có thể là **kết quả nghiệp vụ dự kiến**, không phải lỗi kỹ thuật phải ném xuyên các tầng. Nếu hợp đồng trả về kết quả có trạng thái, hãy giữ mô hình đó; chỉ dùng exception khi thực sự thích hợp với ý nghĩa và trách nhiệm xử lý của API.

## 13. Chọn `throw e`, `throw new ...`, hay xử lý tại chỗ

Câu hỏi nên hỏi là: **Tầng hiện tại đã xử lý xong hậu quả của exception chưa, và caller kỳ vọng loại tín hiệu nào?**

| Tình huống | Lựa chọn thường phù hợp | Hệ quả |
| --- | --- | --- |
| Không có công việc gì cần làm ở tầng này | Không tạo `catch` dư thừa | Exception tự lan truyền |
| Cần ghi nhận ngữ cảnh nhưng giữ loại lỗi nguyên bản | `catch (... e) { ...; throw e; }` | Cùng đối tượng lan lên caller |
| Tầng hiện tại biết cách phục hồi an toàn | `catch` và xử lý hoàn toàn, không rethrow | Lời gọi có thể hoàn tất bình thường |
| API ở tầng cao cần lỗi có mức trừu tượng khác | `throw new DomainOrServiceException(..., e)` | Tạo exception mới, giữ lỗi gốc ở cause |
| Lỗi là kết quả dự kiến của nghiệp vụ | Trả giá trị/kiểu kết quả rõ ràng nếu hợp đồng chọn cách đó | Caller xử lý theo nhánh bình thường |
| Checked exception vẫn cần đi qua tầng trung gian | `throw e` và `throws` tương ứng | Nghĩa vụ checked exception vẫn còn |
| Cần kiểm soát retry | Viết chính sách retry có giới hạn và hiểu side effect; hết khả năng thì rethrow | Retry là hành động mới, không phát sinh do `throw e` |

Một nguyên tắc thiết kế hữu ích: **không dùng rethrow để che giấu trách nhiệm, nhưng cũng không ép tầng thấp tự quyết định phản hồi mà nó không có đủ thông tin**. Caller cần một tín hiệu chính xác để biết thao tác đã hoàn tất hay vẫn đang lỗi.

## 14. Câu hỏi kiểm tra kiến thức

**Câu 1.** Trong `catch (IOException e) { throw e; }`, `throw e` có tạo `IOException` mới không?  
**Đáp án:** Không. Nó ném lại đúng đối tượng được tham chiếu bởi `e`. Caller có thể nhận chính cùng instance đó.

**Câu 2.** Sau khi `throw e` ở handler, câu lệnh nằm ngay sau nó trong handler có chạy không?  
**Đáp án:** Không theo đường thực thi đó. Exception lại lan truyền ra ngoài; đoạn mã trực tiếp không thể tới có thể bị compiler báo lỗi.

**Câu 3.** `throw e` có thay đổi message, cause và stack trace không?  
**Đáp án:** Bản thân lệnh không tạo object mới hay tự thay đổi chúng. Mã khác có thể đã thay đổi thuộc tính được phép sửa của object, và một số cơ chế JVM có ngoại lệ về biểu diễn stack trace.

**Câu 4.** `catch (Exception e) { throw e; }` có luôn buộc phương thức khai báo `throws Exception` không?  
**Đáp án:** Không. Khi `e` là `final` hoặc effectively final, quy tắc precise rethrow có thể cho phép compiler thu hẹp tập checked exception có thể ném từ `try`; ví dụ chỉ cần `throws IOException` nếu đó là loại checked liên quan.

**Câu 5.** Tại sao `throw new IllegalStateException("...", e)` không tương đương `throw e`?  
**Đáp án:** Nó tạo instance mới, đổi loại top-level và giữ `e` làm cause; `throw e` giữ nguyên instance và loại runtime của exception ban đầu.

**Câu 6.** Nếu `finally` ném exception mới trong lúc `catch` đang thực hiện `throw e` thì caller nhận exception nào?  
**Đáp án:** Exception mới từ `finally` có thể thay thế exception đang được ném lại, làm lỗi ban đầu bị che. Đó là lý do không ném lỗi mới vô ý trong cleanup.

**Câu 7.** Nếu handler của `try-with-resources` ném lại bằng `throw e`, tài nguyên đã đóng chưa?  
**Đáp án:** Các tài nguyên được khai báo trong chính `try-with-resources` đã được cố gắng đóng trước khi handler `catch` gắn với cấu trúc đó chạy; lỗi đóng có thể được ghi dạng suppressed.

**Câu 8.** `throw e` có tự thử lại thao tác vừa lỗi không?  
**Đáp án:** Không. Rethrow chuyển tín hiệu lỗi lên tầng khác; retry cần mã gọi lại thao tác theo chính sách.

**Câu 9.** Ném lại unchecked exception có bắt buộc khai báo `throws` không?  
**Đáp án:** Không. `RuntimeException`, `Error` và các lớp con là unchecked, bất kể ném lần đầu hay ném lại.

**Câu 10.** Nếu `catch` không thể khôi phục, không có thông tin bổ sung và chỉ gọi `throw e`, có nên giữ handler đó không?  
**Đáp án:** Thường không cần. Để exception tự lan truyền sẽ đơn giản hơn, miễn là cleanup và hợp đồng được bảo đảm ở nơi phù hợp.

## 15. Checklist khi review mã có `throw e`

Khi đọc một handler ném lại ngoại lệ, tự kiểm tra:

1. **Nguồn lỗi:** Exception này xuất phát từ thao tác nào, loại runtime thực là gì, có checked hay unchecked?
2. **Công việc handler:** Tầng này làm gì thực sự có ích trước khi ném lại? Có đang log cùng lỗi quá nhiều lần không?
3. **Identity và dữ liệu:** Có giữ đúng `e` hay vô tình tạo/gán một instance mới? Message, cause, stack trace, suppressed có bị sửa gây khó chẩn đoán không?
4. **Hợp đồng:** Phương thức đã khai báo các checked exception cần thiết chưa? Có tận dụng precise rethrow an toàn mà không gán lại tham số `catch` không?
5. **Luồng thực thi:** Có lệnh nào sau điểm ném bị bỏ qua? Caller xử lý ở đâu, và liệu `finally`/cleanup có thể che exception gốc?
6. **Phục hồi:** Caller có khả năng xử lý lỗi hay chỉ tiếp tục ném vô tận? Có điểm chịu trách nhiệm cuối cùng ở ranh giới ứng dụng không?
7. **Nguồn dữ liệu:** Đây là tình huống lỗi bất thường hay một kết quả nghiệp vụ hợp lệ nên biểu diễn bằng giá trị rõ ràng?
8. **Kiểm thử:** Đã thử đường ném lại, đường bắt ở caller, cleanup khi lỗi, và checked exception trong chữ ký chưa?

## 16. Kết luận

**`throw e` ném lại cùng đối tượng exception đã được bắt.** Nó bảo toàn identity và loại runtime của exception gốc, thường giữ nguyên thông tin message, cause và stack trace, đồng thời làm handler hiện tại kết thúc bất thường để lỗi tiếp tục đi lên tầng có thể xử lý. Lệnh này **không** tự retry thao tác, **không** tạo wrapper mới và **không** có nghĩa tầng hiện tại đã phục hồi thành công.

Khi exception là checked, vẫn phải tuân thủ `catch-or-declare`; cơ chế *precise rethrow* của Java cho phép một số handler bắt kiểu rộng nhưng khai báo tập checked exception hẹp hơn, nếu tham số `catch` không bị gán lại. Khi cần đổi tầng trừu tượng hoặc thông điệp, hãy dùng wrapper mới **có cause** thay vì nhầm nó với rethrow nguyên bản. Và khi không có việc gì cần làm trước rethrow, để exception tự lan truyền thường là thiết kế gọn hơn.

Nguyên tắc quan trọng để quyết định là: **xử lý khi biết cách phục hồi; ném lại khi phải giữ lỗi gốc cho tầng có trách nhiệm; bọc lỗi khi hợp đồng ở tầng mới yêu cầu một loại tín hiệu khác.**
