# Lan truyền ngoại lệ dọc theo ngăn xếp lời gọi trong Java

Khi một phương thức Java ném ngoại lệ nhưng không có khối `catch` phù hợp để xử lý, ngoại lệ **truyền ngược theo chuỗi lời gọi**. Java lần lượt rời các ngữ cảnh thực thi, thực hiện những khối `finally` hoặc thao tác đóng tài nguyên cần thiết, rồi tìm nơi bắt ngoại lệ phù hợp gần nhất. Quá trình này thường gọi là **exception propagation** và **stack unwinding** (tháo dỡ ngăn xếp lời gọi).

Hiểu cơ chế này giúp bạn giải thích vì sao một lỗi ở tầng đọc dữ liệu lại được bắt tại tầng điều phối; vì sao các câu lệnh sau `throw` không chạy; vì sao `finally` vẫn hoạt động; và vì sao stack trace chứa tên của nhiều phương thức dù ngoại lệ chỉ được ném tại một vị trí.

## 1. Ngăn xếp lời gọi và hướng ngoại lệ di chuyển

Mỗi lời gọi phương thức đang hoạt động có một **stack frame** logic chứa trạng thái thực thi, biến cục bộ và thông tin để quay lại nơi gọi. Giả sử luồng đang đi theo chuỗi:

~~~text
main() gọi outer()
    outer() gọi middle()
        middle() gọi deepest()
            deepest() ném IllegalStateException
~~~

Có thể hình dung trạng thái trước thời điểm ném như sau:

~~~text
Đỉnh call stack
┌───────────────────────────────────────────────┐
│ deepest()       ← ngoại lệ phát sinh ở đây     │
├───────────────────────────────────────────────┤
│ middle()        ← không có catch phù hợp       │
├───────────────────────────────────────────────┤
│ outer()         ← có catch phù hợp             │
├───────────────────────────────────────────────┤
│ main()          ← gọi outer()                  │
└───────────────────────────────────────────────┘
Đáy call stack

Đường lan truyền: deepest() → middle() → outer()
~~~

Các ý cần phân biệt:

- **Luồng gọi** đi từ người gọi đến phương thức được gọi: `main → outer → middle → deepest`.
- **Ngoại lệ chưa được xử lý** đi theo hướng ngược lại: `deepest → middle → outer → main`, cho đến khi gặp một bộ xử lý phù hợp hoặc hết ngăn xếp của luồng.
- Ngoại lệ là một **đối tượng `Throwable`** được ném ra. Nó không tự động tạo thành ngoại lệ mới ở từng tầng.
- Khi một phương thức kết thúc bất thường do ngoại lệ, phương thức ấy **không trả về giá trị bình thường**, dù chữ ký khai báo có kiểu trả về.
- Ngăn xếp dùng để tìm `catch` là ngăn xếp **thực thi động**: điều quan trọng là những lời gọi hiện đang bao quanh thao tác lỗi, không chỉ là quan hệ lớp hay vị trí chữ viết trong tệp nguồn.

Java Language Specification §11.3 mô tả việc tìm `catch` gần nhất bao quanh động và có thể xử lý giá trị ngoại lệ. Phần `try`/`catch`/`finally` được đặc tả chi tiết tại §14.20.

## 2. Runtime làm gì khi gặp một ngoại lệ?

Xét một lệnh như `throw new IllegalStateException("kết nối thất bại");`, hoặc một API tự phát sinh ngoại lệ. Các bước về mặt ngữ nghĩa:

1. **Hoạt động bình thường dừng tại điểm ném:** những câu lệnh còn lại trên đường đi bình thường của khối đang thực thi bị bỏ qua.
2. **Xét bộ xử lý trong ngữ cảnh hiện tại:** runtime tìm `catch` của các khối `try` bao quanh phù hợp với *kiểu thực tế* của đối tượng ngoại lệ.
3. **Nếu không có bộ xử lý phù hợp:** thực hiện những hành động bắt buộc khi rời ngữ cảnh (ví dụ `finally`, đóng tài nguyên do `try-with-resources` quản lý), rồi kết thúc bất thường lời gọi hiện tại.
4. **Quay lại ngữ cảnh gọi:** lời gọi ở tầng trước cũng kết thúc bất thường; việc tìm `catch` tiếp tục tại vị trí lời gọi đó.
5. **Khi gặp `catch` phù hợp:** khối `catch` được chạy. Nếu nó hoàn thành bình thường, quá trình lan truyền của ngoại lệ này kết thúc. Nếu nó lại `throw`, ngoại lệ tiếp tục lan truyền theo đường mới.
6. **Nếu không tầng nào bắt:** ngoại lệ thoát ra khỏi phương thức đầu vào của luồng; cơ chế xử lý ngoại lệ chưa bắt (`UncaughtExceptionHandler`) của luồng được áp dụng và luồng kết thúc.

Đây là mô hình về **luồng điều khiển**: không phải mỗi tầng “tự động ghi log”, không phải mỗi tầng tự động thêm thông báo vào ngoại lệ, và không có việc JVM chạy tất cả `catch` trên đường về. Chỉ khối `catch` phù hợp được chọn theo quy tắc ngôn ngữ; các `finally` liên quan vẫn được thực hiện trong quá trình rời khối.

## 3. Ví dụ Java 17+ hoàn chỉnh: ngoại lệ vượt qua tầng giữa

Lưu nội dung sau trong tệp `PropagationDemo.java`:

~~~java
public class PropagationDemo {
    static String deepest() {
        System.out.println("3. deepest chạy");
        throw new IllegalStateException("kết nối thất bại");
    }

    static String middle() {
        try {
            System.out.println("2. middle chạy");
            return deepest();
        } finally {
            System.out.println("4. finally của middle");
        }
    }

    static void outer() {
        try {
            System.out.println("1. outer chạy");
            System.out.println(middle());
            System.out.println("Dòng này không chạy");
        } catch (IllegalStateException ex) {
            System.out.println("5. outer bắt: " + ex.getMessage());
        } finally {
            System.out.println("6. finally của outer");
        }
    }

    public static void main(String[] args) {
        outer();
        System.out.println("7. Sau outer");
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 PropagationDemo.java
java PropagationDemo
~~~

Kết quả stdout chính xác:

~~~text
1. outer chạy
2. middle chạy
3. deepest chạy
4. finally của middle
5. outer bắt: kết nối thất bại
6. finally của outer
7. Sau outer
~~~

**Vì sao theo đúng thứ tự này?**

- `main()` gọi `outer()`; `outer()` đi vào `try` và gọi `middle()`.
- `middle()` đi vào `try`, sau đó gọi `deepest()`. `deepest()` ném `IllegalStateException` và không trở về với một `String`.
- `middle()` không có `catch`, nhưng có `finally`. JVM thực thi `finally` của `middle()` trước khi chuyển ngoại lệ ra khỏi lời gọi `middle()`.
- `outer()` có `catch (IllegalStateException ex)` bao quanh vị trí gọi `middle()`, vì vậy xử lý ngoại lệ và in dòng 5. Biểu thức `System.out.println(middle())` **không in kết quả nào** vì phần tính đối số `middle()` đã thất bại.
- `finally` của `outer()` in dòng 6. Phương thức `outer()` kết thúc bình thường vì `catch` đã xử lý ngoại lệ, và `main()` in dòng 7.

Hãy chú ý: câu lệnh `System.out.println("Dòng này không chạy")` không chạy vì thuộc đoạn của `try` sau lời gọi ném lỗi. Ngược lại, câu lệnh `System.out.println("7. Sau outer")` chạy vì nằm **sau** một lời gọi đã xử lý xong ngoại lệ.

Không thể mong `deepest()` thực hiện nốt những câu lệnh sau `throw`, cũng không thể mong `middle()` trả về giá trị khi `deepest()` kết thúc bất thường.

## 4. Khi nào quá trình lan truyền dừng, khi nào tiếp tục?

### 4.1. Bắt đúng kiểu sẽ kết thúc đường lan truyền hiện tại

Một `catch` được chọn dựa trên kiểu runtime của đối tượng ngoại lệ và quan hệ kế thừa. Ví dụ, `catch (RuntimeException ex)` có thể bắt `IllegalStateException`, vì `IllegalStateException extends RuntimeException`. `catch (IOException ex)` không bắt được `IllegalStateException`.

Trong một `try`, Java chọn **khối `catch` đầu tiên phù hợp**. Viết các `catch` từ kiểu con đến kiểu cha:

~~~java
// Đoạn minh họa nằm trong một phương thức.
try {
    throw new IllegalArgumentException("dữ liệu không hợp lệ");
} catch (IllegalArgumentException ex) {
    System.out.println("Sai đối số");
} catch (RuntimeException ex) {
    System.out.println("Lỗi runtime khác");
}
~~~

Đầu ra là `Sai đối số`. Không có bước tự chạy tiếp sang `catch (RuntimeException)` sau khi khối thứ nhất hoàn thành. Nếu đặt `catch (RuntimeException)` trước `catch (IllegalArgumentException)`, mã không biên dịch vì nhánh cụ thể ở sau không thể được chọn.

### 4.2. Bắt rồi ném lại: tiếp tục lan truyền

Một `catch` có thể ghi thêm ngữ cảnh hoặc dọn dẹp rồi ném lại chính đối tượng ngoại lệ:

~~~java
// Đoạn minh họa trong một phương thức.
try {
    callDownstream();
} catch (IllegalStateException ex) {
    System.err.println("Lỗi tại tầng trung gian");
    throw ex;
}
~~~

`throw ex;` tiếp tục lan truyền **cùng đối tượng**. Nó không giống `throw new IllegalStateException(...)` vì cách thứ hai tạo đối tượng khác; nếu cần bọc ngoại lệ, hãy truyền `ex` làm `cause`.

Nếu `catch` chỉ in log và kết thúc bình thường, lỗi coi như đã được xử lý tại đó. Người gọi không tự động nhận lại ngoại lệ. Vì vậy phải có chủ đích rõ ràng: xử lý thực sự, ném tiếp hoặc bọc lại; đừng ghi log rồi giả vờ thao tác đã thành công.

### 4.3. Ném loại ngoại lệ khác tại tầng giữa

Ví dụ phương thức thao tác cấu hình đọc tệp và chuyển lỗi I/O thành một thông điệp ở tầng nghiệp vụ:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

// Đoạn minh họa đặt trong một lớp.
static String loadConfig(Path path) {
    try {
        return Files.readString(path);
    } catch (IOException ex) {
        throw new IllegalStateException("Không nạp được cấu hình: " + path, ex);
    }
}
~~~

`loadConfig` đã bắt `IOException` và ném ngoại lệ runtime mới. Người gọi sẽ nhìn thấy `IllegalStateException` là ngoại lệ ngoài cùng; `getCause()` trả về `IOException` gốc. Khi in stack trace, bạn thường thấy một phần `Caused by:` cho chuỗi nguyên nhân.

Việc bọc lỗi chỉ phù hợp khi tầng hiện tại bổ sung ý nghĩa hữu ích. Trong nhiều API I/O, giữ `throws IOException` có thể đơn giản và rõ hợp đồng hơn.

## 5. Checked và unchecked: cùng cách lan truyền runtime, khác kiểm tra biên dịch

Cả `IOException` (checked) và `IllegalStateException` (unchecked) đều có thể vượt qua nhiều lời gọi bằng cơ chế runtime như đã mô tả. Khác biệt nằm ở **quy tắc biên dịch**:

- Với checked exception như `IOException`, mỗi phương thức có thể để ngoại lệ thoát ra phải khai báo kiểu checked phù hợp trong `throws`, trừ khi đã bắt nó hoặc nó không thể phát sinh qua luồng điều khiển của phương thức.
- Với unchecked exception như `IllegalStateException`, `NullPointerException` và các lớp con `Error`, không bắt buộc có `throws` mặc dù chúng vẫn có thể truyền qua call stack.
- `throws` thông báo trách nhiệm cho **mã gọi ở thời điểm biên dịch**. Nó không tạo ra nhánh xử lý runtime và không chặn ngoại lệ.

Ví dụ checked exception hợp lệ:

~~~java
import java.io.IOException;

// Các phương thức nằm trong cùng một lớp.
static void lowLevel() throws IOException {
    throw new IOException("không thể đọc");
}

static void middleLevel() throws IOException {
    lowLevel();
}

static void topLevel() {
    try {
        middleLevel();
    } catch (IOException ex) {
        System.out.println(ex.getMessage());
    }
}
~~~

Khi `topLevel()` được gọi, stdout là `không thể đọc`. Nếu bỏ `throws IOException` khỏi `middleLevel()`, đoạn trên sẽ lỗi biên dịch kiểu `unreported exception IOException; must be caught or declared to be thrown`. Điều này là yêu cầu tại **định nghĩa** `middleLevel`, không phụ thuộc vào việc `topLevel` cuối cùng đã bắt lỗi.

## 6. Tác động của `finally` trong lúc tháo dỡ stack

`finally` được thực thi khi rời `try`/`catch` liên quan, dù rời do hoàn thành bình thường, `return` hay ném ngoại lệ. Đây là lý do quan trọng khiến việc “quay ngược call stack” không đồng nghĩa với bỏ qua toàn bộ mã ở các tầng giữa.

~~~java
// Đoạn minh họa bên trong một phương thức.
try {
    throw new IllegalStateException("lỗi gốc");
} finally {
    System.out.println("Dọn dẹp trước khi truyền lỗi");
}
~~~

Khối `finally` in dòng thông báo rồi ngoại lệ vẫn được truyền ra ngoài (do `finally` hoàn thành bình thường). Thứ tự này có thể lặp lại ở nhiều lời gọi, từ `finally` của tầng sâu lên `finally` của tầng nông.

**Cảnh báo về ngoại lệ bị che lấp:** nếu chính `finally` ném ngoại lệ khác, hoặc thực hiện `return`, nguyên nhân thoát khối ban đầu có thể bị thay thế. Ví dụ sau có kết quả trả về `2` dù khối `try` đã chuẩn bị `return 1`:

~~~java
// Đoạn minh họa không nên dùng trong thiết kế thực tế.
static int unsafeReturn() {
    try {
        return 1;
    } finally {
        return 2;
    }
}
~~~

Nguy hiểm hơn, `return` hoặc `throw` trong `finally` có thể che đi ngoại lệ thật sự đang lan truyền. Chỉ đặt công việc dọn dẹp phù hợp ở `finally`, và tránh viết luồng điều khiển kết thúc đột ngột tại đây.

`finally` là cơ chế đảm bảo theo ngữ nghĩa Java khi khối được rời một cách thông thường hoặc bất thường; nó **không phải lời hứa tuyệt đối** nếu JVM hoặc tiến trình bị dừng cưỡng bức, chẳng hạn `Runtime.halt` hay mất điện.

## 7. `try-with-resources`: ngoại lệ chính và ngoại lệ bị suppressed

Để quản lý đối tượng `AutoCloseable`, `try-with-resources` giúp gọi `close()` tự động khi rời khối. Các tài nguyên được đóng theo **thứ tự ngược với thứ tự khởi tạo thành công**.

Có thể cả thân `try` lẫn `close()` đều ném ngoại lệ. Trong trường hợp đó, Java ưu tiên giữ ngoại lệ chính từ thân `try`; ngoại lệ trong lúc đóng được ghi dưới dạng **suppressed exception** (truy xuất qua `getSuppressed()`), thay vì che khuất lỗi chính như một `finally` viết thiếu cẩn thận.

Chương trình độc lập `SuppressedDemo.java`:

~~~java
public class SuppressedDemo {
    static class BrokenResource implements AutoCloseable {
        @Override
        public void close() throws Exception {
            throw new Exception("lỗi đóng");
        }
    }

    public static void main(String[] args) {
        try (BrokenResource resource = new BrokenResource()) {
            throw new Exception("lỗi xử lý");
        } catch (Exception ex) {
            System.out.println("Chính: " + ex.getMessage());
            System.out.println("Suppressed: " + ex.getSuppressed()[0].getMessage());
        }
    }
}
~~~

Chạy bằng:

~~~bash
javac -encoding UTF-8 SuppressedDemo.java
java SuppressedDemo
~~~

Stdout:

~~~text
Chính: lỗi xử lý
Suppressed: lỗi đóng
~~~

Nếu thân `try` không ném ngoại lệ nhưng `close()` ném, ngoại lệ từ `close()` có thể trở thành ngoại lệ đang lan truyền. Khi đọc stack trace từ code có nhiều tài nguyên, cần kiểm tra cả `Caused by` (chuỗi nguyên nhân) lẫn `Suppressed` (các lỗi phụ khi đóng tài nguyên); chúng không phải cùng một quan hệ.

## 8. Đọc stack trace để truy ra đường gọi

`Throwable.printStackTrace()` in loại ngoại lệ, thông điệp và các khung stack liên quan. Với một ngoại lệ được tạo trong `deepest()` và phát sinh khi đang gọi từ `middle()`, `outer()`, dạng có thể giống như:

~~~text
java.lang.IllegalStateException: kết nối thất bại
    at PropagationDemo.deepest(PropagationDemo.java:4)
    at PropagationDemo.middle(PropagationDemo.java:10)
    at PropagationDemo.outer(PropagationDemo.java:19)
    at PropagationDemo.main(PropagationDemo.java:29)
~~~

Đây là **minh họa định dạng**, không phải stdout của chương trình `PropagationDemo` ở mục 3 (vì chương trình đó đã bắt ngoại lệ và chỉ in `getMessage()`). Số dòng trong stack trace phụ thuộc chính xác vào mã nguồn đã lưu và môi trường; không nên suy luận chúng từ ví dụ minh họa.

Khi phân tích trace:

1. Dòng đầu cho biết **loại ngoại lệ và thông điệp**.
2. Khung ở trên cùng thường chỉ vị trí stack trace được ghi nhận khi đối tượng ngoại lệ được tạo hoặc `fillInStackTrace()` được gọi; các khung dưới thể hiện chuỗi lời gọi vào thời điểm đó.
3. Đọc từ trên xuống để lần về các tầng gọi; đọc từ dưới lên để thấy đường đi vào lời gọi dẫn tới lỗi.
4. Nếu có `Caused by:`, lần theo nguyên nhân sâu hơn; lỗi ngoài cùng có thể chỉ là lớp bọc của lỗi gốc.
5. Nếu có `Suppressed:`, xem các lỗi phụ xảy ra khi thu dọn tài nguyên.

Một điểm thường bị hiểu nhầm: **việc lan truyền không tự động chồng thêm frame vào stack trace ở mỗi lần `throw ex;`**. Đối tượng ngoại lệ mang dấu vết được ghi lại khi tạo hoặc khi cập nhật stack trace, thường tại tầng sâu. Khi tạo ngoại lệ bọc mới, ngoại lệ bọc có stack trace riêng ở điểm bọc; ngoại lệ gốc vẫn được nối bằng `cause`.

Để chẩn đoán tốt, nên ghi log toàn bộ ngoại lệ một lần ở ranh giới chịu trách nhiệm báo lỗi (truyền chính đối tượng cho logger để giữ trace), và thêm ngữ cảnh khi chuyển tầng. Ghi log rồi ném lại ở mọi tầng thường tạo bản ghi trùng lặp mà không thêm giá trị.

## 9. Lan truyền có vượt qua ranh giới luồng không?

**Không tự động.** Call stack thuộc về một luồng đang thực thi; ngoại lệ trong luồng con không quay ngược vào stack của luồng đã gọi `Thread.start()`.

~~~java
// Đoạn minh họa: catch bên ngoài start() không bắt lỗi trong task.
try {
    Thread worker = new Thread(() -> {
        throw new IllegalStateException("lỗi của worker");
    });
    worker.start();
} catch (IllegalStateException ex) {
    // Không xử lý ngoại lệ phát sinh sau đó trong luồng worker.
}
~~~

Lời gọi `start()` diễn ra ở luồng gọi và chủ yếu bắt đầu một luồng khác. Ngoại lệ xuất hiện khi lambda thực thi trên **call stack riêng** của `worker`. Nếu worker không tự xử lý, ngoại lệ đi tới `UncaughtExceptionHandler` của worker; `catch` quanh `start()` không nhận nó.

Tương tự, khi dùng `ExecutorService.submit(Callable)`, lỗi trong tác vụ thường được giữ trong `Future`; khi gọi `future.get()`, bên nhận có thể gặp **`ExecutionException`**, lấy lỗi tác vụ bằng `getCause()`. Với `CompletableFuture.join()`, lỗi bất thường thường được phản ánh qua **`CompletionException`**. Cơ chế này chuyển **thông tin lỗi qua kết quả tác vụ**, không phải ném cùng ngoại lệ xuyên qua hai call stack độc lập.

Điều này quan trọng khi debug ứng dụng có thread pool, callback hoặc tác vụ bất đồng bộ: cần tìm nơi thực thi task, nơi thu kết quả và lớp bọc ngoại lệ; không thể chỉ đặt một `try/catch` ở vị trí khởi chạy rồi kỳ vọng bắt mọi lỗi tương lai.

## 10. Nếu không có `catch` nào phù hợp thì sao?

Đối với lời gọi đồng bộ, khi một ngoại lệ không được bắt trong toàn bộ đường gọi hiện tại, nó đạt đến ranh giới thực thi của luồng. JVM áp dụng cơ chế `Thread.UncaughtExceptionHandler` đã cấu hình; handler mặc định thường in thông tin lỗi và stack trace ra luồng lỗi chuẩn. Luồng bị kết thúc do ngoại lệ chưa bắt.

Nếu đó là luồng `main` duy nhất của một chương trình đơn giản, tiến trình thường kết thúc. Nếu là luồng worker, những luồng khác không nhất thiết dừng theo; hành vi cấp ứng dụng còn phụ thuộc cách quản lý luồng và tác vụ. Một số framework/executor **thu giữ lỗi** và trả về dưới dạng kết quả bất thường thay vì để nó đi tới handler mặc định.

Không nên dùng `catch (Throwable)` hoặc `catch (Error)` rộng ở mọi nơi để “ngăn chương trình dừng”: những lỗi nghiêm trọng của JVM có thể không thể phục hồi. Hãy bắt các ngoại lệ thực sự có cách xử lý; thiết lập xử lý lỗi ở ranh giới ứng dụng theo đúng yêu cầu quan sát và vận hành.

## 11. Những lỗi suy luận và lỗi thiết kế thường gặp

| Nhầm lẫn | Thực tế | Cách xử lý |
| --- | --- | --- |
| Ngoại lệ luôn bị bắt ngay ở phương thức ném | Nó được tìm từ ngữ cảnh gần nhất ra các tầng gọi. | Vẽ chuỗi lời gọi và đánh dấu phạm vi `try`. |
| Sau `throw`, chương trình chạy tiếp phần còn lại của `try` | Đường thực thi bình thường dừng; các `finally` phù hợp vẫn chạy. | Truy vết riêng luồng bình thường và bất thường. |
| `throws` giải quyết hoặc nuốt lỗi | `throws` chỉ khai báo với compiler, không bắt tại runtime. | Đặt `catch` ở tầng có phương án xử lý thực sự. |
| Mọi `catch` tương thích trên đường truyền đều chạy | Chỉ bộ xử lý phù hợp gần nhất được chọn cho lần ném đó. | Ghi lại nơi `catch` hoàn thành hoặc ném tiếp. |
| `finally` không liên quan tới ngoại lệ | Nó chạy trong quá trình rời khối và có thể ảnh hưởng đường lan truyền. | Dọn dẹp an toàn; tránh `return`/`throw` che lỗi gốc. |
| `throw ex` luôn cập nhật stack trace tại nơi ném lại | Ném lại cùng đối tượng thường giữ trace cũ. | Dùng `cause` khi cần tạo ngoại lệ mới kèm ngữ cảnh. |
| `catch` bên ngoài `thread.start()` bắt lỗi trong luồng mới | Mỗi luồng có call stack riêng. | Xử lý lỗi bên trong task hoặc đọc kết quả Future. |
| Ghi log cùng lỗi ở mọi tầng giúp debug tốt hơn | Dễ sinh nhiều bản ghi cho một sự cố. | Bọc đủ ngữ cảnh và log một lần tại điểm quan sát phù hợp. |
| Ngoại lệ từ `close()` luôn thay thế lỗi xử lý | `try-with-resources` có cơ chế suppressed exception. | Kiểm tra `getSuppressed()` cùng `getCause()`. |

Một cách debug thực tế là đánh dấu ba vị trí: **điểm ném**, **những khối dọn dẹp trên đường truyền**, và **điểm bắt**. Nếu không có điểm bắt, xác định ranh giới luồng hoặc cơ chế thực thi tác vụ nhận lỗi. Sau đó truy nguyên `cause` và `suppressed` để không bỏ sót nguyên nhân ban đầu.

## 12. Câu hỏi tự kiểm tra

1. **A gọi B, B gọi C, C ném `RuntimeException`. B không có `catch`, A bắt `RuntimeException`. Ai xử lý?** — A xử lý; ngoại lệ đi C → B → A, trừ khi B có đoạn `finally` làm thay đổi đường thoát.
2. **`return` sau lời gọi thất bại có chạy không?** — Không, nếu ngoại lệ chưa được bắt bên trong lời gọi/biểu thức tương ứng.
3. **Nếu B có `finally` và A có `catch`, thứ tự là gì?** — `finally` của B hoàn tất trước khi quyền điều khiển chuyển đến `catch` của A, giả sử `finally` không kết thúc bất thường.
4. **`catch (Exception)` có bắt `Error` không?** — Không; `Error` không phải lớp con của `Exception`.
5. **Ném lại cùng đối tượng bằng `throw ex` có tạo ngoại lệ mới không?** — Không; đây là cùng một đối tượng, giữ dấu vết sẵn có trừ khi bị cập nhật tường minh.
6. **`try (resource)` có thể giữ đồng thời lỗi trong body và lỗi `close()` không?** — Có, lỗi đóng có thể nằm trong `getSuppressed()` của lỗi chính.
7. **Lỗi trong `Callable` chạy bằng executor có nhảy trực tiếp vào `catch` quanh `submit()` không?** — Không; thường phải kiểm tra `Future.get()` và `ExecutionException.getCause()`.

## Tài liệu đối chiếu

- Java Language Specification 17, [§11.3 — Run-Time Handling of an Exception](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.3): cơ chế tìm `catch` trong ngữ cảnh thực thi.
- Java Language Specification 17, [§14.18 — The throw Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.18): cách một câu lệnh `throw` kết thúc bất thường.
- Java Language Specification 17, [§14.20 — The try Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20): lựa chọn `catch`, thực thi `finally` và `try-with-resources`.
- Java SE 17 API, [Throwable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): `getCause()`, `getSuppressed()`, `printStackTrace()`.
- Java SE 17 API, [Thread.UncaughtExceptionHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.UncaughtExceptionHandler.html) và [Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): cách quan sát lỗi ở ranh giới luồng/tác vụ.

Cốt lõi: ngoại lệ đi ngược **các lời gọi đang hoạt động** để tìm `catch` tương thích gần nhất; việc tháo dỡ stack vẫn tuân theo quy tắc `finally` và đóng tài nguyên, còn việc xử lý hoặc ném tiếp tại tầng bắt quyết định luồng thực thi sau đó.
