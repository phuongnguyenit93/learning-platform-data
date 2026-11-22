# Kiểm tra checked exception và các nhánh xử lý trong biên dịch Java

Một chương trình Java có thể đúng cú pháp, tìm được tất cả kiểu và phương thức nhưng vẫn không biên dịch được vì một nhánh mã có khả năng phát sinh **checked exception** mà không được xử lý hoặc khai báo. Đây là một phần của **kiểm tra ngữ nghĩa** do `javac` thực hiện: trình biên dịch phân tích các biểu thức, lời gọi, lệnh `throw`, khối `try/catch/finally` và các đường đi qua chương trình để quyết định một ngoại lệ đã được xử lý hay còn có thể thoát khỏi phương thức.

Mục tiêu của bài là hiểu **vì sao compiler chấp nhận hoặc từ chối một cấu trúc xử lý ngoại lệ**, đồng thời phân biệt điều compiler có thể kiểm tra từ kiểu khai báo với điều thực sự xảy ra khi chạy.

## 1. Checked exception là gì?

Mọi ngoại lệ trong Java đều liên quan đến hệ phân cấp `Throwable`:

~~~text
java.lang.Throwable
├── java.lang.Error
│   └── ... (lỗi hệ thống, thường không nên bắt để phục hồi)
└── java.lang.Exception
    ├── java.lang.RuntimeException
    │   ├── IllegalArgumentException
    │   └── NullPointerException
    ├── java.io.IOException
    │   └── java.io.FileNotFoundException
    └── java.sql.SQLException
~~~

Trong quy tắc kiểm tra exception của ngôn ngữ:

- **Checked exception** là các lớp con của `Throwable` **không** thuộc `RuntimeException` hay `Error` (bao gồm trực tiếp `Throwable` và `Exception`). Các ví dụ quen thuộc: `IOException`, `SQLException`, `ClassNotFoundException` và các ngoại lệ nghiệp vụ tùy chỉnh kế thừa `Exception`.
- **Unchecked exception** là `RuntimeException` và các lớp con của nó, hoặc `Error` và các lớp con. Compiler không buộc mọi lời gọi có khả năng gây `NullPointerException` phải viết `catch`/`throws`.
- Việc một ngoại lệ là checked hay unchecked dựa trên **quan hệ kế thừa kiểu**, không dựa vào tên class, mô tả lỗi hay việc chương trình có thể phục hồi được hay không.

Ví dụ:

~~~java
import java.io.IOException;

class StorageException extends IOException {
    StorageException(String message) {
        super(message);
    }
}

class InputProblem extends RuntimeException {
    InputProblem(String message) {
        super(message);
    }
}
~~~

`StorageException` là checked vì kế thừa `IOException`; `InputProblem` là unchecked vì kế thừa `RuntimeException`. Đoạn trên là **minh họa khai báo kiểu** và chưa có `main`; không cần chạy như chương trình độc lập.

**Hai cách đáp ứng kiểm tra của compiler:** xử lý checked exception bằng nhánh `catch` phù hợp (có thể chuyển đổi thành kết quả hoặc ném loại ngoại lệ khác), hoặc khai báo ngoại lệ có thể thoát bằng mệnh đề `throws` ở phương thức/constructor thích hợp. Trong một số ngữ cảnh như lambda, quy tắc còn phụ thuộc kiểu hàm đích.

## 2. Phân biệt throw, throws, try và catch

| Cấu trúc | Ý nghĩa | Compiler kiểm tra gì? |
| --- | --- | --- |
| `throw new IOException("x");` | **Ném** một đối tượng ngoại lệ tại vị trí thực thi | Ngoại lệ checked có được xử lý hoặc cho phép thoát không? Biểu thức có kiểu con của `Throwable` không? |
| `void read() throws IOException` | **Khai báo** khả năng phương thức hoàn tất đột ngột do ngoại lệ | Mọi checked exception có thể thoát đều phù hợp với kiểu trong `throws` |
| `try { ... } catch (IOException e) { ... }` | Xử lý ngoại lệ phù hợp phát sinh từ vùng `try` | Catch có thể bắt loại ngoại lệ được phép? Thứ tự catch có tạo nhánh không thể tới không? |
| `finally { ... }` | Thực hiện hành động cuối của `try` theo quy tắc hoàn tất bình thường/đột ngột | Các nhánh cuối có thể kết thúc thế nào, có checked exception mới thoát ra không? |
| `try (Resource r = ...) { ... }` | Tự đóng tài nguyên qua `AutoCloseable` | Cả phần tạo/sử dụng/đóng resource có thể phát sinh checked exception nào? |

Mệnh đề `throws` **không tự bắt** ngoại lệ và không bảo đảm ngoại lệ sẽ thực sự xảy ra. Nó tạo ra một hợp đồng tĩnh cho người gọi: nếu kiểu phương thức khai báo `throws IOException`, người gọi phải xử lý hoặc khai báo `IOException`, ngay cả khi một implementation cụ thể hiếm khi ném nó.

Ngoài ra, `throws` được phép liệt kê checked exception mà phương thức thực tế không ném (trừ các ràng buộc đặc biệt như override). Đây là một hợp đồng cho phép ngoại lệ thoát, không phải bản ghi mọi trường hợp runtime.

## 3. Ví dụ Java 17+: hai nhánh xử lý thành công và thất bại

**Tệp `ExceptionBranchesDemo.java`** hoàn chỉnh:

~~~java
import java.io.IOException;

public final class ExceptionBranchesDemo {
    static String read(boolean shouldFail) throws IOException {
        if (shouldFail) {
            throw new IOException("read failed");
        }
        return "content";
    }

    static String execute(boolean shouldFail) {
        try {
            return read(shouldFail);
        } catch (IOException ex) {
            return "fallback:" + ex.getMessage();
        } finally {
            System.out.println("cleanup");
        }
    }

    public static void main(String[] args) {
        System.out.println(execute(false));
        System.out.println(execute(true));
    }
}
~~~

Biên dịch và chạy tại thư mục chứa tệp:

~~~bash
javac -encoding UTF-8 ExceptionBranchesDemo.java
java ExceptionBranchesDemo
~~~

**Stdout chính xác:**

~~~text
cleanup
content
cleanup
fallback:read failed
~~~

**Vì sao biên dịch được?**

1. `read` có nhánh `if` ném `IOException`; phương thức khai báo `throws IOException` nên cho phép loại checked exception ấy thoát.
2. `execute` gọi `read` trong `try`, và `catch (IOException ex)` có thể xử lý đúng loại ngoại lệ được khai báo. Vì vậy `execute` không cần `throws IOException` nếu không có đường thoát checked exception khác.
3. Khi `shouldFail=false`, `read` trả về `content`. Trước khi `execute` hoàn tất `return`, `finally` in `cleanup`. Sau đó `main` in `content`.
4. Khi `shouldFail=true`, `throw` chuyển điều khiển sang `catch` để tạo chuỗi `fallback:read failed`; `finally` vẫn chạy trước khi giá trị trả về đến `main`.
5. Compiler kiểm tra cả hai khả năng điều khiển dựa trên mã và kiểu khai báo; compiler không cần chạy chương trình hoặc biết trước giá trị truyền vào.

**Không có yêu cầu phải bắt mọi unchecked exception** như `NullPointerException` có thể phát sinh từ việc truy cập đối tượng rỗng. Việc biên dịch thành công không chứng minh mọi đường chạy sẽ tránh được lỗi.

## 4. Trường hợp compiler từ chối vì thiếu xử lý

Đoạn sau **cố ý sai, không phải chương trình chạy được**:

~~~java
import java.io.IOException;

class MissingHandling {
    static void read() throws IOException {
        throw new IOException("disk");
    }

    static void run() {
        read(); // Lỗi: checked IOException chưa được xử lý/khai báo.
    }
}
~~~

`run()` không có `throws IOException` và cũng không có `try/catch`. `javac` có thể báo theo dạng:

~~~text
error: unreported exception IOException; must be caught or declared to be thrown
~~~

Vị trí/dòng báo lỗi thay đổi theo tên tệp, JDK và cách viết. Có ba cách hợp lệ về mặt ngôn ngữ, với ý nghĩa thiết kế khác nhau.

**Cách A – Xử lý ngay tại nơi gọi:**

~~~java
static void run() {
    try {
        read();
    } catch (IOException ex) {
        System.err.println("Read failed: " + ex.getMessage());
    }
}
~~~

**Cách B – Chuyển trách nhiệm cho người gọi tiếp theo:**

~~~java
static void run() throws IOException {
    read();
}
~~~

**Cách C – Chuyển thành ngoại lệ unchecked có nguyên nhân:**

~~~java
static void run() {
    try {
        read();
    } catch (IOException ex) {
        throw new IllegalStateException("Cannot read", ex);
    }
}
~~~

Ba đoạn này là **thay thế cho thân phương thức `run`** trong `MissingHandling`, không phải ba chương trình độc lập. Cách C giữ ngoại lệ gốc trong `cause` để thuận tiện chẩn đoán; chỉ nên dùng khi API thực sự muốn chuyển loại lỗi. Trong ứng dụng thực tế, ghi log rồi nuốt ngoại lệ có thể không đủ; xử lý phải phù hợp hành vi nghiệp vụ, cơ chế retry hoặc chính sách lỗi của lớp hiện tại.

## 5. Phân tích các nhánh if, switch và lời gọi

Compiler phân tích khả năng ngoại lệ phát sinh từ biểu thức và câu lệnh trên các nhánh. Một phương thức **không** thoát khỏi quy tắc checked exception chỉ vì một nhánh lỗi “hiếm xảy ra”.

Đoạn **cố ý sai**:

~~~java
import java.io.IOException;

class BranchCheck {
    static String load() throws IOException {
        return "ok";
    }

    static String select(boolean fromDisk) {
        if (fromDisk) {
            return load(); // Chưa bắt/khai báo IOException.
        }
        return "memory";
    }
}
~~~

Dù runtime thường truyền `false`, tham số `fromDisk` có thể là `true`; `select` cần `throws IOException` hoặc xử lý trong nhánh liên quan. Cách sửa giữ hợp đồng của `select` không có `throws`:

~~~java
static String select(boolean fromDisk) {
    if (!fromDisk) {
        return "memory";
    }
    try {
        return load();
    } catch (IOException ex) {
        return "fallback";
    }
}
~~~

**Phần sửa chỉ là thân method thay thế trong class `BranchCheck`.** Bản thân các đoạn này chưa có phương thức `main`.

Những trường hợp tương tự:

- `if/else`: ngoại lệ checked có thể thoát từ **bất kỳ** nhánh liên quan nào cần được xử lý hoặc khai báo.
- `switch` và `switch expression`: các case có thể gọi những phương thức khai báo các ngoại lệ khác nhau. Cả case trả về giá trị và case `throw` đều chịu quy tắc kiểm tra ngoại lệ.
- Vòng lặp: compiler vẫn kiểm tra ngoại lệ từ thân vòng lặp và các biểu thức liên quan; đừng xem `break`/`continue` là cách miễn xử lý checked exception.
- Tham số phương thức: chữ ký `throws` của một method được xét tại vị trí gọi, không phụ thuộc giả định rằng dữ liệu đầu vào luôn “tốt”.
- Nhánh `return` sớm: ngoại lệ ném **trước** `return` vẫn phải được giải quyết; `finally` có thể chạy trên đường hoàn tất ấy.

Phân tích ngữ nghĩa không tương đương với static analyzer chứng minh mọi điều kiện runtime. Đừng dựa vào việc compiler tối ưu hóa điều kiện để thiết kế quy tắc xử lý ngoại lệ.

## 6. Catch theo kiểu: subtype và thứ tự nhánh

Một `catch` xử lý đối tượng ngoại lệ tương thích với kiểu bắt. Khi có nhiều catch, JVM chọn **nhánh phù hợp đầu tiên theo thứ tự xuất hiện**.

Ví dụ hợp lệ:

~~~java
try {
    performIO();
} catch (java.io.FileNotFoundException ex) {
    System.out.println("File missing");
} catch (java.io.IOException ex) {
    System.out.println("Other IO failure");
}
~~~

`performIO()` ở đây là lời gọi **minh họa**, được giả định có thể ném `FileNotFoundException` hoặc `IOException` khác. Kiểu con `FileNotFoundException` đặt **trước** kiểu cha `IOException` nên mỗi nhánh có cơ hội xử lý đúng ngoại lệ.

Đảo thứ tự là **cố ý sai**:

~~~java
try {
    performIO();
} catch (java.io.IOException ex) {
    System.out.println("IO failure");
} catch (java.io.FileNotFoundException ex) {
    System.out.println("Missing file"); // Catch không thể đến.
}
~~~

`FileNotFoundException` là lớp con của `IOException` nên đã bị catch đầu tiên bao phủ. Compiler báo nhánh bắt sau không thể đạt tới (thường là “exception ... has already been caught”). Nguyên tắc xếp nhánh: **loại cụ thể trước, loại rộng hơn sau**.

### Catch checked exception mà try không thể ném

Đoạn này **cố ý sai**:

~~~java
try {
    int answer = 40 + 2;
    System.out.println(answer);
} catch (java.io.IOException ex) {
    System.out.println("Cannot happen here");
}
~~~

Các câu lệnh trong `try` không khai báo/ném `IOException`, nên `javac` thường báo `exception IOException is never thrown in body of corresponding try statement`.

Tuy nhiên cần phân biệt trường hợp catch `Exception` hoặc unchecked exception: Java có các quy tắc đặc biệt cho các kiểu có thể bao gồm unchecked exception, nên **không** suy rộng ví dụ trên thành “mọi catch không có throw tường minh đều sai”. Nếu `try` gọi phương thức khai báo `throws IOException`, catch đó có thể hợp lệ dù implementation runtime của phương thức không ném ngoại lệ trong lần gọi đang xét.

### Không catch theo “tên giống nhau”

Nếu hai thư viện khai báo hai class ngoại lệ cùng simple name nhưng khác package, chúng vẫn là hai kiểu khác nhau. Compiler phân giải tên kiểu trong `catch` qua package/import như với các type khác. Hãy dùng tên đầy đủ khi cần loại bỏ mơ hồ.

## 7. Multi-catch cho các nhánh xử lý giống nhau

Từ Java 7, `catch (IOException | SQLException ex)` bắt cả hai kiểu trong một khối. Đây là cú pháp gọn hơn khi **cùng cách phục hồi/ghi nhận lỗi**.

**Tệp `MultiCatchDemo.java`:**

~~~java
import java.io.IOException;
import java.sql.SQLException;

public final class MultiCatchDemo {
    static String query(int mode) throws IOException, SQLException {
        if (mode == 1) {
            throw new IOException("disk");
        }
        if (mode == 2) {
            throw new SQLException("database");
        }
        return "ok";
    }

    public static void main(String[] args) {
        for (int mode = 0; mode <= 2; mode++) {
            try {
                System.out.println(query(mode));
            } catch (IOException | SQLException ex) {
                System.out.println(
                        ex.getClass().getSimpleName() + ":" + ex.getMessage()
                );
            }
        }
    }
}
~~~

Biên dịch/chạy Java 17+:

~~~bash
javac -encoding UTF-8 MultiCatchDemo.java
java MultiCatchDemo
~~~

**Stdout chính xác:**

~~~text
ok
IOException:disk
SQLException:database
~~~

Phân tích:

- `query` có hai nhánh ném hai loại checked exception, nên liệt kê cả `IOException` và `SQLException` trong `throws`.
- Multi-catch ở `main` xử lý cả hai loại, vì vậy `main` không cần `throws` tương ứng.
- Biến `ex` của multi-catch là **implicitly final**: không được gán lại.
- Các alternative trong cùng multi-catch không được có quan hệ lớp con/lớp cha với nhau.

Ví dụ **cố ý sai**:

~~~java
catch (java.io.FileNotFoundException | java.io.IOException ex) {
    // Sai: FileNotFoundException là subtype của IOException.
}
~~~

Compiler báo các alternative không hợp lệ do quan hệ subtype. Chọn `catch (IOException ex)` hoặc tách các catch theo thứ tự hợp lệ.

Một câu hỏi quan trọng: multi-catch không có nghĩa compiler bỏ qua phân tích các exception có thể phát sinh từ **thân catch**. Nếu bên trong khối catch gọi phương thức ném checked exception khác, vẫn phải xử lý/khai báo ngoại lệ đó.

## 8. Checked exception phát sinh bên trong catch và finally

Xử lý một ngoại lệ có thể gây ngoại lệ mới. Compiler phân tích **mỗi vùng mã**, gồm thân `catch` và `finally`, thay vì chỉ phân tích khối `try` ban đầu.

Đoạn **minh họa cố ý sai**:

~~~java
import java.io.IOException;
import java.sql.SQLException;

class HandlerCheck {
    static void risky() throws IOException {
        throw new IOException("read");
    }

    static void persist() throws SQLException {
        throw new SQLException("save");
    }

    static void handle() {
        try {
            risky();
        } catch (IOException ex) {
            persist(); // SQLException chưa xử lý hoặc khai báo.
        }
    }
}
~~~

`catch` giải quyết `IOException` của `risky`, nhưng `persist` khai báo `SQLException`. Vì `handle` không catch/throws loại mới, compiler từ chối.

Một sửa chữa hợp lệ là thêm `throws SQLException` vào `handle` hoặc bắt `SQLException` trong một `try/catch` khác tại thân catch. Không nên đổi thành `catch (Exception)` một cách máy móc nếu sự cố ghi dữ liệu cần cách xử lý riêng.

Với `finally`, ví dụ:

~~~java
static void cleanup() throws IOException {
    throw new IOException("close");
}

static void work() {
    try {
        System.out.println("work");
    } finally {
        cleanup(); // Cố ý sai: IOException từ finally không được xử lý.
    }
}
~~~

Các method ở đoạn thứ hai chỉ là **mã minh họa ở bên trong một class**. Dù thân `try` không ném checked exception, `finally` vẫn có thể ném `IOException` nên `work` phải bắt/khai báo nó.

**Điểm cần nhớ:** `finally` thông thường vẫn chạy khi khối `try`/`catch` chuẩn bị `return` hoặc `throw`; nhưng nếu JVM kết thúc bất thường ngoài khả năng thực thi Java bình thường (ví dụ process bị chấm dứt), không bảo đảm hành động dọn dẹp diễn ra. Nếu `finally` tự ném một exception hoặc `return`, nó có thể thay thế kết quả/exception đang được chuyển ra ngoài. Tránh viết `return` hay `throw` để vô tình che lỗi gốc trong `finally`.

## 9. Try-with-resources và ngoại lệ từ close()

Dùng `try-with-resources` khi đối tượng triển khai `AutoCloseable`. Cấu trúc này gọi `close()` tự động khi thoát khỏi khối, bao gồm khi có `return` hoặc ngoại lệ.

**Tệp `ResourceDemo.java`:**

~~~java
import java.io.IOException;

public final class ResourceDemo {
    static final class TrackedResource implements AutoCloseable {
        String read(boolean fail) throws IOException {
            if (fail) {
                throw new IOException("read failed");
            }
            return "data";
        }

        @Override
        public void close() throws IOException {
            System.out.println("closed");
        }
    }

    static String execute(boolean fail) {
        try (TrackedResource resource = new TrackedResource()) {
            return resource.read(fail);
        } catch (IOException ex) {
            return "caught:" + ex.getMessage();
        }
    }

    public static void main(String[] args) {
        System.out.println(execute(false));
        System.out.println(execute(true));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 ResourceDemo.java
java ResourceDemo
~~~

**Stdout chính xác:**

~~~text
closed
data
closed
caught:read failed
~~~

Trong ví dụ, `read` **và** `close` đều có khai báo `throws IOException`. Compiler phải tính ngoại lệ từ cả việc sử dụng resource và việc đóng resource. `catch (IOException ex)` xử lý hai nguồn tiềm năng, do đó `execute` không cần khai báo checked exception. Việc `close` hiện chỉ in ra console không khiến compiler tự bỏ qua chữ ký `throws IOException`.

Nếu resource có `close() throws Exception` (kiểu rộng hơn `IOException`), một catch chỉ nhận `IOException` có thể không đủ; phải dựa vào **kiểu được khai báo** của `close` để thiết kế catch/throws phù hợp.

### Suppressed exception: giữ lỗi gốc khi close cũng lỗi

Nếu phần thân `try` ném ngoại lệ và `close()` cũng ném, try-with-resources thường giữ exception của phần thân làm **primary exception** và đính ngoại lệ từ close vào `getSuppressed()`.

**Tệp `SuppressedDemo.java`:**

~~~java
import java.io.IOException;

public final class SuppressedDemo {
    static final class BrokenResource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("close");
        }
    }

    public static void main(String[] args) {
        try (BrokenResource resource = new BrokenResource()) {
            throw new IOException("body");
        } catch (IOException ex) {
            System.out.println(ex.getMessage());
            for (Throwable suppressed : ex.getSuppressed()) {
                System.out.println("suppressed:" + suppressed.getMessage());
            }
        }
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 SuppressedDemo.java
java SuppressedDemo
~~~

**Stdout chính xác:**

~~~text
body
suppressed:close
~~~

Đây là hành vi khác với việc tự đóng tài nguyên trong `finally` rồi để ngoại lệ từ `close` vô tình che lỗi xảy ra trước. Khi ghi log ngoại lệ chính, nên giữ thông tin suppressed để không làm mất nguyên nhân phụ.

Nếu nhiều resource được khai báo trong try-with-resources, chúng được đóng theo **thứ tự ngược với thứ tự khai báo**. Các checked exception từ việc khởi tạo và đóng các resource cũng tham gia phân tích exception.

## 10. Rethrow và phân tích kiểu chính xác hơn

Java có cơ chế **precise rethrow**: trong một số điều kiện, compiler suy luận được rằng một biến exception bắt theo kiểu rộng thực tế chỉ có thể chứa các loại checked exception cụ thể phát sinh từ khối `try`.

**Tệp `RethrowDemo.java`:**

~~~java
import java.io.IOException;

public final class RethrowDemo {
    static void action(boolean fail) throws IOException {
        try {
            if (fail) {
                throw new IOException("failed");
            }
        } catch (Exception ex) {
            throw ex;
        }
    }

    public static void main(String[] args) {
        try {
            action(true);
        } catch (IOException ex) {
            System.out.println(ex.getMessage());
        }
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 RethrowDemo.java
java RethrowDemo
~~~

Stdout:

~~~text
failed
~~~

Bề ngoài `ex` có kiểu `Exception`, nhưng compiler có thể suy ra ngoại lệ checked được ném từ `try` ở đây chỉ là `IOException`, nên `action` khai báo `throws IOException` là đủ. Điều này dựa trên quy tắc precise rethrow, không phải “mọi `catch (Exception)` luôn tương đương `catch (IOException)`”.

Precise rethrow có điều kiện, trong đó biến parameter của `catch` phải không bị gán lại (effectively final). Nếu đổi giá trị của `ex` rồi `throw ex`, khả năng suy luận kiểu ngoại lệ có thể khác và chữ ký `throws IOException` có thể không đủ.

## 11. Checked exception trong override và triển khai interface

Một phương thức override **không được mở rộng tùy ý tập checked exception** so với phương thức bị override. Nó có thể bỏ mệnh đề `throws`, hoặc khai báo các checked exception tương thích hẹp hơn theo quy tắc Java.

**Tệp `OverrideDemo.java`:**

~~~java
import java.io.IOException;

interface TextReader {
    String read() throws IOException;
}

final class FixedReader implements TextReader {
    @Override
    public String read() {
        return "ready";
    }
}

public final class OverrideDemo {
    public static void main(String[] args) throws IOException {
        TextReader reader = new FixedReader();
        System.out.println(reader.read());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 OverrideDemo.java
java OverrideDemo
~~~

Stdout:

~~~text
ready
~~~

Trong implementation `FixedReader.read` không cần `throws IOException` vì không có checked exception thoát ra. Nhưng tại lời gọi `reader.read()`, biến `reader` có **kiểu compile-time `TextReader`**, và chữ ký interface khai báo `throws IOException`. Vì thế `main` cần catch/throws `IOException` dù object runtime là `FixedReader`.

Đoạn **cố ý sai** khi thay implementation:

~~~java
final class InvalidReader implements TextReader {
    @Override
    public String read() throws Exception {
        return "ready";
    }
}
~~~

`Exception` rộng hơn `IOException`; compiler từ chối override vì checked exception khai báo rộng hơn hợp đồng interface. Nếu muốn khai báo loại checked exception hẹp hơn, một override có thể dùng `FileNotFoundException` (lớp con của `IOException`) nếu thân phương thức phù hợp.

Ngược lại, thêm `throws IllegalArgumentException` (unchecked) không bị hạn chế bởi quy tắc narrowing checked exception này, dù API vẫn nên có hợp đồng rõ ràng.

Đối với phương thức override nhiều khai báo từ các interface/superclass, tập checked exception hợp lệ còn phải tương thích với **mọi** hợp đồng mà phương thức triển khai.

## 12. Checked exception trong lambda và functional interface

Lambda được kiểm tra theo **target type** (kiểu functional interface) chứa chữ ký abstract method. Một lambda không thể tự thêm checked exception nếu phương thức đích không cho phép nó.

Ví dụ **cố ý sai**:

~~~java
import java.io.IOException;

java.util.function.RunnableTask task = () -> {
    throw new IOException("disk");
};
~~~

Đoạn trên còn dùng sai tên interface: Java chuẩn có `java.lang.Runnable`, không phải `java.util.function.RunnableTask`. Khi sửa về đúng interface, **vẫn** có lỗi checked exception vì `Runnable.run()` không khai báo checked exception:

~~~java
Runnable task = () -> {
    throw new java.io.IOException("disk"); // Cố ý sai: Runnable.run không throws IOException.
};
~~~

Cách thiết kế đúng nếu tác vụ thực sự cần ném checked exception là chọn một functional interface có chữ ký phù hợp hoặc tự định nghĩa:

~~~java
@FunctionalInterface
interface IoAction {
    void run() throws java.io.IOException;
}

IoAction action = () -> {
    throw new java.io.IOException("disk");
};
~~~

Hai đoạn cuối chỉ minh họa lambda trong **ngữ cảnh có khai báo biến**, không phải chương trình `main` độc lập. Khi gọi `action.run()`, người gọi lại phải bắt hoặc khai báo `IOException`.

Ví dụ chuẩn: `java.util.concurrent.Callable<V>.call() throws Exception` cho phép thân lambda khai báo/ném checked exception phù hợp, còn `Runnable.run()` thì không. Khi dùng các lambda với `Stream.map` hoặc `Function.apply`, cần đọc chữ ký functional interface thay vì giả định có thể ném checked exception tùy ý.

## 13. Constructor, field initializer và exception ở những vị trí khác

Checked exception không chỉ xuất hiện trong lời gọi method thông thường. Compiler cũng kiểm tra các vị trí khác, ví dụ:

- **Constructor**: nếu thân constructor hoặc initializer liên quan có checked exception có thể thoát, hợp đồng constructor cần khai báo ngoại lệ tương ứng; mọi nơi gọi constructor phải xử lý/khai báo.
- **Khởi tạo field và instance initializer**: quy tắc ngoại lệ phụ thuộc ngữ cảnh initializer và constructor. Một checked exception phát sinh trong instance initialization có thể đòi hỏi khai báo phù hợp ở các constructor; không thể tùy tiện “để nó tự thoát” như trong một method có `throws`.
- **Static initializer**: không có chữ ký `throws` để chuyển checked exception ra ngoài theo cách thông thường. Nếu static initializer gọi một phương thức ném checked exception, phải xử lý thích hợp trong block; lỗi runtime của quá trình khởi tạo lớp là vấn đề khác.
- **Biểu thức tạo object**: `new SomeType()` có thể phải xử lý checked exception do constructor khai báo.
- **Method reference**: cũng chịu kiểm tra tính tương thích với functional interface mục tiêu, gồm các loại ngoại lệ có thể thoát.

**Tệp `ConstructorDemo.java`**:

~~~java
import java.io.IOException;

final class ConnectionLike {
    ConnectionLike(boolean fail) throws IOException {
        if (fail) {
            throw new IOException("open failed");
        }
    }
}

public final class ConstructorDemo {
    public static void main(String[] args) {
        try {
            new ConnectionLike(true);
        } catch (IOException ex) {
            System.out.println(ex.getMessage());
        }
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 ConstructorDemo.java
java ConstructorDemo
~~~

Stdout:

~~~text
open failed
~~~

`new ConnectionLike(true)` chính là biểu thức có checked exception theo khai báo constructor. `catch` ở `main` xử lý loại ngoại lệ ấy; nếu bỏ catch và không thêm throws, compiler sẽ từ chối.

## 14. Checked exception, quyền kiểm tra compile và ngoại lệ runtime

Không phải lỗi ngoại lệ nào cũng xuất hiện trong lần biên dịch:

| Tình huống | Compiler bắt buộc phát hiện? | Ví dụ |
| --- | --- | --- |
| Gọi method `throws IOException` mà không catch/throws | Có | Lỗi checked exception ở source |
| `catch (FileNotFoundException)` sau `catch (IOException)` | Có | Nhánh catch cụ thể đã bị catch cha che |
| `catch (IOException)` khi try không thể ném loại checked đó | Thường có theo quy tắc reachability của catch | Lỗi catch không phù hợp |
| `throw new RuntimeException()` không catch/throws | Không bắt buộc catch/throws | Unchecked |
| Null receiver gây `NullPointerException` | Không phải compiler luôn chứng minh được | Có thể ném khi chạy |
| Đóng resource lỗi hoặc I/O ngoài dự kiến | Compiler kiểm tra kiểu khai báo; runtime quyết định lỗi thực tế | `IOException` khi đọc/đóng |
| Phiên bản thư viện runtime khác bản compile | Thường không phát hiện tại compile source với thư viện cũ | `NoSuchMethodError` / `NoClassDefFoundError` lúc chạy |

Chỉ vì method khai báo `throws IOException` **không có nghĩa** runtime luôn ném ngoại lệ đó. Và method **không khai báo checked exception** vẫn có thể ném các unchecked exception. Compiler tập trung bảo đảm hợp đồng ngoại lệ checked của mã nguồn, không dự đoán mọi sự cố trong vận hành.

Ngoại lệ được bắt mà xử lý không phù hợp cũng có thể gây lỗi nghiệp vụ. Ví dụ:

~~~java
try {
    saveData();
} catch (Exception ignored) {
    // Nuốt toàn bộ lỗi có thể che mất dữ liệu chưa lưu.
}
~~~

Đây là đoạn minh họa; `saveData` giả định là một lời gọi có thể ném ngoại lệ. Cú pháp có thể hợp lệ nhưng không có nghĩa là cách xử lý tốt. Khi catch để chuyển lỗi, nên giữ `cause` và ghi nhận ngữ cảnh phù hợp.

## 15. Quy tắc kiểm tra nhánh: sơ đồ quyết định thực hành

~~~text
Phát hiện lời gọi/throw/tạo resource có thể ném E
                 |
                 v
       E có phải checked không?
          /                 \
         Không              Có
          |                  |
   Không bắt buộc       E có thể thoát
   catch/throws         khỏi vùng try?
                           |
                          \/
                  Catch nào tương thích?
                      /           \
                     Có           Không
                     |              |
              Phân tích thân       Method/constructor
              catch, finally      có throws bao phủ E?
                     |              /      \
                     |             Có      Không
                     |             |         |
              Ngoại lệ mới       Hợp lệ   Compile error
              có thể thoát?        |
                     |        Người gọi tiếp tục
              Kiểm tra tiếp    chịu trách nhiệm
~~~

Đây là **mô hình tư duy**, không phải thuật toán nội bộ chính xác của `javac`. Compiler phân tích cú pháp, kiểu và luồng điều khiển cùng nhau; một `catch` có thể không hợp lệ vì thứ tự, kiểu hoặc khả năng ngoại lệ phát sinh. Quan trọng là truy dấu được checked exception từ **nguồn phát sinh** qua các **nhánh có thể xử lý** đến **hợp đồng method/constructor**.

Một cách đọc lỗi hữu ích:

1. **Xác định loại ngoại lệ chính xác** trong thông báo compiler: `IOException`, `SQLException` hay một subtype khác?
2. **Tìm nguồn phát sinh**: `throw`, method/constructor `throws`, lời gọi trong catch/finally, hoặc `close()` của resource.
3. **Đánh giá tất cả đường đi khả dĩ**: một nhánh `if`, case `switch`, thân loop, cleanup và khối catch lồng nhau có khiến ngoại lệ thoát không?
4. **Đọc thứ tự catch**: subtype phải đặt trước supertype, và catch phải có ngữ nghĩa phù hợp với exception mà vùng try có thể ném.
5. **Xem chữ ký hiện tại**: catch để phục hồi tại đây, hay `throws` để tầng gọi giải quyết? Nếu override, chữ ký có tuân thủ hợp đồng cha/interface không?
6. **Sau khi biên dịch được**, kiểm tra logic xử lý runtime: đảm bảo không nuốt lỗi, không che nguyên nhân gốc và đóng tài nguyên đúng cách.

## 16. Bài tập tự kiểm tra có đáp án

### Bài 1: nhánh throw không được khai báo

~~~java
static void run(boolean fail) {
    if (fail) {
        throw new java.io.IOException("disk");
    }
}
~~~

**Câu hỏi:** Đoạn trên biên dịch không? **Đáp án:** Không, vì `IOException` là checked và có thể thoát khỏi `run`. Sửa bằng `throws IOException` (cùng import nếu muốn viết tên ngắn) hoặc bắt loại ngoại lệ thích hợp trong method.

### Bài 2: thứ tự catch

~~~java
try {
    readFile();
} catch (java.io.IOException ex) {
    recover();
} catch (java.io.FileNotFoundException ex) {
    reportMissing();
}
~~~

**Câu hỏi:** Vì sao catch thứ hai sai? **Đáp án:** `FileNotFoundException` là subtype của `IOException`; ngoại lệ của kiểu này đã bị nhánh thứ nhất bắt. Đưa catch cụ thể lên trước nếu các method minh họa có chữ ký và xử lý phù hợp.

### Bài 3: override và lời gọi qua interface

Interface khai báo `void load() throws IOException`; implementation override `void load()` không throws. Một biến có kiểu **interface** gọi `load()`. Có cần catch/throws không?

**Đáp án:** Có, vì compiler xét chữ ký của kiểu compile-time của receiver. Implementation cụ thể không throws không xóa hợp đồng checked exception của interface khỏi lời gọi đó.

### Bài 4: close phát sinh IOException

Một resource implements `AutoCloseable` có `close() throws IOException` nhưng thân `try` chỉ in ra console. Có thể bỏ catch/throws `IOException` không?

**Đáp án:** Không, nếu checked exception từ `close` có thể thoát khỏi cấu trúc try-with-resources. Compiler còn xét chữ ký `close()`, không chỉ phần thân `try`.

### Bài 5: multi-catch

Hai ngoại lệ `IOException` và `SQLException` không có quan hệ cha con. Có thể dùng `catch (IOException | SQLException ex)` không? Có, nếu chúng là các loại ngoại lệ có thể được catch hợp lệ từ vùng `try`; biến `ex` không được gán lại.

### Bài 6: finally ghi đè exception

Nếu phần thân `try` ném `IOException("read")`, nhưng `finally` lại ném `IllegalStateException("cleanup")`, loại ngoại lệ nào thoát ra bình thường?

**Đáp án:** Exception từ `finally` có thể thay thế/che ngoại lệ đang được chuyển ra từ `try`. Cần tránh việc cleanup tùy tiện ghi đè nguyên nhân đầu tiên; với tài nguyên, try-with-resources hỗ trợ suppressed exceptions.

## Ghi nhớ để áp dụng

- Checked exception là quy tắc **kiểu và luồng điều khiển tại compile-time**, không phải dự đoán runtime.
- `throw` làm phát sinh ngoại lệ; `throws` khai báo khả năng thoát; `catch` xử lý loại tương thích; `finally` và `close()` có thể đưa thêm ngoại lệ vào phân tích.
- Compiler xét các nhánh có thể xảy ra trong `if`, `switch`, loop, catch và finally. Một đường thoát checked exception chưa được catch/throws là lỗi biên dịch.
- Catch cụ thể đứng trước catch rộng; multi-catch không được chứa những alternative có quan hệ subtype; catch checked exception phải hợp lệ với vùng `try`.
- Try-with-resources kiểm tra ngoại lệ từ việc tạo, dùng và đóng tài nguyên; suppressed exception giúp giữ lỗi từ `close` khi thân `try` đã ném ngoại lệ.
- Overriding không được khai báo checked exception rộng hơn hợp đồng kế thừa; lambda phụ thuộc chữ ký ngoại lệ của functional interface.
- Khi gặp `unreported exception`, truy từ nguồn ngoại lệ qua tất cả nhánh đến chữ ký method, chọn catch để xử lý tại chỗ hoặc `throws` để chuyển trách nhiệm lên trên.
