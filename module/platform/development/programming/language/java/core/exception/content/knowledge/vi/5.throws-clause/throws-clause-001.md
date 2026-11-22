# Cú pháp `throws` trên phương thức và constructor trong Java

Mệnh đề **`throws`** nằm trong phần khai báo một **phương thức (method)** hoặc **constructor** để chỉ ra các loại ngoại lệ mà lời gọi có thể truyền ra cho mã gọi. Đây là một phần trong hợp đồng của API, đặc biệt quan trọng với **checked exception**: trình biên dịch buộc mã gọi phải bắt ngoại lệ hoặc tiếp tục khai báo ngoại lệ thích hợp.

Cần phân biệt ba khái niệm ngay từ đầu:

- `new IOException("...")` **tạo một đối tượng ngoại lệ**.
- `throw new IOException("...");` **ném** đối tượng, làm luồng thực thi hiện tại kết thúc bất thường.
- `void read() throws IOException { ... }` **khai báo** khả năng phương thức có thể để ngoại lệ `IOException` thoát ra. Chỉ khai báo `throws` không tạo, ném hay xử lý ngoại lệ.

Bài này hướng dẫn viết đúng vị trí, danh sách và kiểu ngoại lệ trong mệnh đề `throws` của phương thức và constructor trên Java 17+, kèm ví dụ chạy được, các quy tắc liên quan khi gọi và kế thừa, cùng lỗi biên dịch phổ biến.

## 1. Cú pháp của `throws` ở phương thức

Dạng tổng quát của một khai báo phương thức có thân:

~~~java
[modifiers] ReturnType methodName(ParameterType parameter, ...)
        throws ExceptionType1, ExceptionType2 {
    // Nội dung phương thức
}
~~~

Trong cú pháp trên:

- `[modifiers]` biểu diễn các từ khóa tùy chọn như `public`, `protected`, `private`, `static` hoặc `final`, tùy ngữ cảnh. Ngoặc vuông chỉ dùng để chú thích công thức, **không gõ nguyên văn** trong Java.
- `ReturnType` là kiểu trả về, hoặc `void`.
- `methodName(...)` là tên và danh sách tham số.
- `throws` đứng **sau dấu `)` kết thúc danh sách tham số**, trước dấu `{` mở phần thân.
- `ExceptionType1, ExceptionType2` là những kiểu ngoại lệ phân cách bởi dấu phẩy, không phải bởi `|`, `+` hoặc `;`.
- Nếu không có ngoại lệ cần khai báo, **bỏ hẳn `throws`**; không viết `throws` với danh sách rỗng.

Ví dụ một ngoại lệ:

~~~java
import java.io.IOException;

// Đặt trong một lớp.
public static String read(String filename) throws IOException {
    return java.nio.file.Files.readString(java.nio.file.Path.of(filename));
}
~~~

Ví dụ nhiều ngoại lệ:

~~~java
import java.io.IOException;
import java.sql.SQLException;

// Mã minh họa chữ ký và việc ném tương ứng, đặt trong một lớp.
static void execute(boolean databaseError) throws IOException, SQLException {
    if (databaseError) {
        throw new SQLException("Database unavailable");
    }
    throw new IOException("Input unavailable");
}
~~~

`throws IOException, SQLException` tạo ra **danh sách kiểu ngoại lệ trong chữ ký**; không có nghĩa mỗi lần gọi đều ném hai lỗi hoặc Java sẽ tự lần lượt phát sinh chúng. Khi phương thức được gọi, chỉ đường thực thi thực tế quyết định ngoại lệ nào xuất hiện.

Các khai báo interface/abstract method không có thân cũng đặt `throws` ở sau tham số, rồi kết thúc bằng dấu `;`:

~~~java
import java.io.IOException;

interface DocumentReader {
    String read() throws IOException;
}

abstract class AbstractImporter {
    public abstract void importData() throws IOException;
}
~~~

`throws` thuộc **khai báo phương thức**, không phải phần riêng của khối `try` hay một câu lệnh có thể chèn vào giữa phần thân.

### Những cách viết đúng và sai

| Cú pháp | Hợp lệ? | Giải thích |
| --- | --- | --- |
| `void work() throws IOException { ... }` | Có | `throws` sau danh sách tham số. |
| `void work() throws IOException, SQLException { ... }` | Có | Danh sách nhiều kiểu, cách nhau bởi dấu phẩy. |
| `void work() { ... }` | Có | Không bắt buộc ghi `throws` nếu không cần khai báo. |
| `void work() throws { ... }` | Không | Danh sách sau `throws` không được để rỗng. |
| `void work() throws IOException | SQLException { ... }` | Không | `|` thuộc cú pháp multi-catch, không dùng trong `throws`. |
| `throws IOException void work() { ... }` | Không | Đặt `throws` sai vị trí. |

Trong bảng, `...` chỉ là ký hiệu rút gọn để nói tới một phần thân hợp lệ, **không phải đoạn mã biên dịch độc lập**.

## 2. Cú pháp của `throws` ở constructor

Constructor cũng có thể ném checked exception khi khởi tạo đối tượng thất bại, ví dụ không mở được tệp, không tải được cấu hình hoặc việc gọi constructor lớp cha thất bại.

Dạng tổng quát:

~~~java
[modifiers] ClassName(ParameterType parameter, ...)
        throws ExceptionType1, ExceptionType2 {
    // Khởi tạo đối tượng
}
~~~

Các điểm riêng của constructor:

1. Tên constructor phải trùng với tên lớp và **không có kiểu trả về** — không ghi `void` hay kiểu đối tượng ở trước tên constructor.
2. `throws` đứng sau danh sách tham số và trước dấu `{`, giống vị trí ở phương thức.
3. Constructor có thể khai báo nhiều checked exception bằng danh sách phân cách dấu phẩy.
4. Constructor không được kế thừa và không thể `override` giống phương thức. Tuy nhiên, constructor của lớp con **gọi constructor lớp cha**, nên phải tuân thủ quy tắc checked exception của lời gọi đó.
5. Khi biểu thức `new SomeClass(...)` gọi một constructor khai báo checked exception, mã gọi phải bắt hoặc khai báo, hệt như gọi phương thức có `throws`.

Ví dụ cú pháp đơn giản:

~~~java
import java.io.IOException;

class ResourceSession {
    ResourceSession(boolean available) throws IOException {
        if (!available) {
            throw new IOException("Cannot open resource");
        }
    }
}
~~~

`new ResourceSession(false)` có thể phát sinh `IOException`, vì vậy nơi gọi phải có `try/catch` phù hợp hoặc khai báo `throws IOException`. Việc `new` là thao tác tạo đối tượng không làm nó được miễn khỏi quy tắc kiểm tra ngoại lệ.

### Sự khác biệt dễ nhận ra giữa method và constructor

~~~java
// Minh họa hai khai báo đặt trong cùng một lớp có tên Example.
Example() throws java.io.IOException {
    // Constructor: không có kiểu trả về.
}

void run() throws java.io.IOException {
    // Phương thức: có kiểu trả về void.
}
~~~

Nếu viết `void Example() throws IOException` bên trong lớp `Example`, đây là **phương thức có tên Example**, không phải constructor. Nên kiểm tra phần kiểu trả về khi một khai báo tưởng như constructor lại có hành vi khác mong đợi.

## 3. Ví dụ hoàn chỉnh: `throws` ở method và constructor

Tạo tệp `ThrowsSyntaxDemo.java`:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class ThrowsSyntaxDemo {
    static class Configuration {
        private final String content;

        Configuration(Path path) throws IOException {
            content = Files.readString(path);
        }

        String content() {
            return content;
        }
    }

    static Configuration load(Path path) throws IOException {
        return new Configuration(path);
    }

    public static void main(String[] args) throws IOException {
        Path path = Files.createTempFile("throws-demo-", ".txt");
        try {
            Files.writeString(path, "Xin chào");
            Configuration config = load(path);
            System.out.println("Nội dung: " + config.content());
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 ThrowsSyntaxDemo.java
java ThrowsSyntaxDemo
~~~

Stdout chính xác khi thao tác tạo/ghi/đọc/xóa tệp tạm thành công:

~~~text
Nội dung: Xin chào
~~~

Giải thích:

1. `Files.createTempFile` tạo tệp tạm; `Files.writeString` ghi dữ liệu. Các API I/O có thể phát sinh `IOException` nên `main` khai báo `throws IOException`.
2. `Configuration(Path path) throws IOException` khai báo checked exception vì lời gọi `Files.readString(path)` có thể thất bại.
3. `load(Path path) throws IOException` gọi `new Configuration(path)`. Nó không bắt `IOException` nên **khai báo để chuyển trách nhiệm lên người gọi**.
4. `main` gọi `load` và tiếp tục chuyển `IOException` ra ngoài nếu có thất bại; `main` không có `catch` đối với loại lỗi này. Do đó, nếu I/O thật sự lỗi và không được bắt ở tầng khác, chương trình thường kết thúc bất thường với stack trace.
5. `content()` chỉ trả lại dữ liệu đã lưu; nó không khai báo `throws` vì đoạn hiện tại không cần cho checked exception nào thoát ra.
6. Khối `finally` gọi `Files.deleteIfExists` để cố gắng xóa tệp tạm. Chính thao tác dọn dẹp này cũng có thể phát sinh `IOException`. Nếu cả phần `try` và `finally` ném lỗi, lỗi từ `finally` có thể che lỗi trước đó; dùng `try-with-resources` khi quản lý các tài nguyên `AutoCloseable` là cách phổ biến để giữ suppressed exception.

Việc dùng tệp tạm cho thấy `throws` là một **cam kết về khả năng thất bại của API**, không phải công cụ tạo lỗi. Trong trường hợp thành công, chương trình in kết quả bình thường mà không có ngoại lệ nào bị ném.

## 4. Người gọi phương thức hoặc constructor có `throws` phải làm gì?

Với **checked exception**, người gọi có hai lựa chọn phổ biến.

### 4.1. Bắt ở nơi có thể xử lý: `try/catch`

~~~java
import java.io.IOException;

// Đặt trong một lớp đã có Configuration và một phương thức logError.
static void start(Path path) {
    try {
        Configuration config = new Configuration(path);
        System.out.println(config.content());
    } catch (IOException ex) {
        logError(ex);
    }
}
~~~

Đây là **đoạn minh họa**, phụ thuộc các khai báo `Path`, `Configuration`, `logError` bên ngoài. Vì đã bắt `IOException`, `start` không bắt buộc khai báo `throws IOException` chỉ do lời gọi này, miễn không có đường checked exception khác thoát ra.

Nơi bắt nên có hành động xử lý hữu ích: báo lỗi cho người dùng, cung cấp đường dự phòng hợp lệ, thêm ngữ cảnh hoặc chuyển trách nhiệm có chủ đích. Không nên `catch (IOException ignored) { }` rồi cư xử như thể hoạt động thành công.

### 4.2. Tiếp tục khai báo `throws`

~~~java
import java.io.IOException;
import java.nio.file.Path;

// Đặt trong lớp có constructor Configuration(Path) throws IOException.
static Configuration start(Path path) throws IOException {
    return new Configuration(path);
}
~~~

Ở đây `start` không xử lý; `IOException` có thể truyền cho người gọi tiếp theo. Nếu nhiều tầng cùng `throws IOException`, lỗi đi ngược chuỗi lời gọi cho tới khi gặp `catch` phù hợp hoặc không còn người bắt.

`throws IOException` có thể bao quát các lớp con checked như `FileNotFoundException` hay `NoSuchFileException`; không nhất thiết phải liệt kê từng lớp con. Nhưng `throws IOException` **không tự bao quát `SQLException`**: hai loại này khác nhánh. Muốn cả hai có thể thoát ra, khai báo cả hai hoặc kiểu cha thích hợp, đồng thời cân nhắc độ rõ ràng của API.

### 4.3. `main` cũng có thể dùng `throws`

Chữ ký `public static void main(String[] args) throws IOException` là hợp lệ. Tuy nhiên, nó **không bắt** ngoại lệ ở ranh giới ứng dụng. Nếu lỗi thực sự thoát từ `main`, nó có thể dẫn tới chấm dứt bất thường và stack trace theo handler mặc định của luồng.

Nếu muốn thông báo thân thiện và mã thoát có kiểm soát, bắt lỗi tại một điểm thích hợp của ứng dụng. Việc viết `throws` chỉ làm trách nhiệm truyền lên tầng gọi rõ ràng về mặt ngôn ngữ.

## 5. Constructor chaining: `this(...)` và `super(...)`

Trong constructor, Java có cơ chế gọi constructor khác trong cùng lớp bằng `this(...)`, hoặc gọi constructor lớp cha bằng `super(...)`. Lời gọi đó có thể ném checked exception nên constructor đang khai báo cũng phải đáp ứng **catch-or-declare**. Trên Java 17, lời gọi constructor tường minh này phải là câu lệnh đầu tiên trong constructor; không thể bọc `super(...)` bằng `try/catch` ở thân constructor để xử lý tại chỗ theo cách thông thường.

### Ví dụ hoàn chỉnh: constructor lớp con khai báo `throws`

Tạo tệp `ConstructorThrowsDemo.java`:

~~~java
import java.io.IOException;

class Resource {
    Resource(boolean available) throws IOException {
        if (!available) {
            throw new IOException("không có tài nguyên");
        }
    }
}

class ManagedResource extends Resource {
    ManagedResource(boolean available) throws IOException {
        super(available);
    }
}

public class ConstructorThrowsDemo {
    public static void main(String[] args) {
        try {
            new ManagedResource(false);
        } catch (IOException ex) {
            System.out.println("Không khởi tạo: " + ex.getMessage());
        }

        try {
            new ManagedResource(true);
            System.out.println("Khởi tạo thành công");
        } catch (IOException ex) {
            System.out.println("Không khởi tạo: " + ex.getMessage());
        }
    }
}
~~~

Lệnh chạy:

~~~bash
javac -encoding UTF-8 ConstructorThrowsDemo.java
java ConstructorThrowsDemo
~~~

Stdout chính xác:

~~~text
Không khởi tạo: không có tài nguyên
Khởi tạo thành công
~~~

Phân tích:

- Constructor `Resource(boolean)` khai báo `throws IOException`. Nếu `available == false`, nó thực hiện `throw new IOException(...)`.
- Constructor `ManagedResource(boolean)` gọi `super(available)`. Vì lời gọi tới constructor lớp cha có thể phát sinh `IOException`, constructor lớp con khai báo `throws IOException`.
- Khi `new ManagedResource(false)` thất bại, việc khởi tạo đối tượng không hoàn tất bình thường; khối `catch` ở `main` xử lý `IOException`.
- Với `true`, không có ngoại lệ nào được ném; quá trình khởi tạo kết thúc bình thường.

Nếu xóa `throws IOException` khỏi `ManagedResource(boolean)` mà vẫn gọi `super(available)`, trình biên dịch báo lỗi checked exception chưa được bắt hoặc khai báo.

Một quy tắc đáng nhớ: **constructor không tham gia quan hệ override**. Không áp dụng quy tắc “constructor con chỉ được khai báo ngoại lệ hẹp hơn constructor cha”. Constructor con có thể khai báo kiểu checked thích hợp theo thao tác của chính nó, miễn các lời gọi cần thiết được xử lý theo luật Java.

### Constructor mặc định và lời gọi `super()` ngầm định

Nếu một lớp không khai báo constructor, trình biên dịch cung cấp **default constructor** theo các quy tắc của Java. Với lớp con, constructor phải gọi constructor lớp cha. Khi constructor không chỉ định `this(...)` hoặc `super(...)`, Java 17 sẽ cố gắng gọi `super()` ngầm định.

Nếu constructor không tham số của lớp cha khai báo checked exception, một lớp con không thể trông chờ vào default constructor để “tự động thêm `throws`”. Cần tự khai báo constructor phù hợp và nêu `throws`:

~~~java
import java.io.IOException;

class Parent {
    Parent() throws IOException {
        throw new IOException("khởi tạo Parent thất bại");
    }
}

class Child extends Parent {
    Child() throws IOException {
        super();
    }
}
~~~

Đây là **đoạn minh họa gồm hai lớp**, chưa có `main`. Nếu lược bỏ hoàn toàn constructor của `Child`, default constructor được tạo không khai báo `throws IOException` nên chương trình có thể lỗi biên dịch do lời gọi `super()` ngầm định.

Với `this(...)`, lý luận tương tự: constructor ủy quyền phải khai báo checked exception có thể truyền ra từ constructor đích. Nếu khởi tạo không thành công ở một mắt xích, chuỗi khởi tạo cũng kết thúc bất thường.

## 6. Checked và unchecked exception tác động đến `throws` như thế nào?

Quy tắc tĩnh quan trọng nhất:

- **Checked exception** là các kiểu `Throwable` không thuộc nhánh `RuntimeException` hoặc `Error`. Nếu phương thức/constructor có thể để chúng thoát ra, compiler thông thường yêu cầu khai báo kiểu checked thích hợp hoặc xử lý bằng `catch`.
- **Unchecked exception** thuộc nhánh `RuntimeException` hoặc `Error`; compiler không bắt buộc khai báo bằng `throws`.
- Cả hai loại đều **có thể** được liệt kê trong `throws`, nhưng liệt kê unchecked thường mang ý nghĩa tài liệu API hơn là nghĩa vụ bắt của mã gọi.

Ví dụ:

~~~java
// Mã minh họa nằm trong một lớp.
static int parse(String raw) {
    return Integer.parseInt(raw); // Có thể ném NumberFormatException, unchecked.
}

static int parseWithDeclaration(String raw)
        throws NumberFormatException {
    return Integer.parseInt(raw);
}
~~~

Cả hai chữ ký hợp lệ. Gọi `parseWithDeclaration` **không bị compiler yêu cầu** `catch (NumberFormatException)` chỉ vì có mệnh đề `throws`, vì đây là unchecked exception.

Ngược lại:

~~~java
import java.io.IOException;

// Đoạn minh họa đặt trong một lớp.
static void checkedFailure() throws IOException {
    throw new IOException("không đọc được");
}
~~~

Một phương thức gọi `checkedFailure()` mà không xử lý `IOException` hoặc khai báo tương ứng sẽ lỗi biên dịch.

**Quan trọng:** cách phân loại checked/unchecked là tính chất của kiểu ngoại lệ, không phải của chữ `throws`. Không có trường hợp “thêm `throws` vào kiểu runtime rồi biến nó thành checked”.

## 7. Khai báo nhiều loại ngoại lệ và kiểu cha

Cú pháp khai báo nhiều kiểu:

~~~java
import java.io.IOException;
import java.sql.SQLException;

// Mã minh họa thuộc một lớp.
static void synchronize(boolean dbMode) throws IOException, SQLException {
    if (dbMode) {
        throw new SQLException("DB error");
    }
    throw new IOException("Network error");
}
~~~

Người gọi cần bao phủ cả hai tình huống nếu chúng có thể truyền ra:

~~~java
// Đoạn minh họa nằm trong phương thức có synchronized(...) ở phạm vi lớp.
try {
    synchronize(true);
} catch (IOException ex) {
    System.out.println("I/O: " + ex.getMessage());
} catch (SQLException ex) {
    System.out.println("SQL: " + ex.getMessage());
}
~~~

Các đoạn ngắn trong phần này cần `import` tương ứng và được đặt bên trong lớp/phương thức; chúng dùng để minh họa chữ ký, không phải tệp Java độc lập.

Bạn cũng có thể viết `throws Exception`, vì `Exception` là kiểu cha của `IOException` và `SQLException`. Cú pháp này hợp lệ nhưng thường giảm độ chính xác hợp đồng API: người gọi khó xác định những lỗi nào có thể phục hồi và dễ phải bắt quá rộng.

Đối với cùng một họ ngoại lệ, `throws IOException` đã bao gồm các lớp con nên thông thường không cần viết `throws IOException, FileNotFoundException` cùng lúc. Có thể khai báo như vậy nhưng lặp về mặt bao phủ; nên ưu tiên loại đủ cụ thể hoặc kiểu cha có ý nghĩa theo mức trừu tượng của API.

Khi khai báo API ổn định, chú ý việc **thêm checked exception mới vào `throws`** có thể khiến mã nguồn của khách hàng không còn biên dịch nếu họ chưa bắt hay khai báo nó.

## 8. `throws` khi ghi đè phương thức và triển khai interface

Khác với constructor, **phương thức override** phải tuân thủ hợp đồng checked exception của phương thức cha hoặc interface.

~~~java
import java.io.FileNotFoundException;
import java.io.IOException;

interface Reader {
    String read() throws IOException;
}

class FileReaderImpl implements Reader {
    @Override
    public String read() throws FileNotFoundException {
        return "OK";
    }
}

class MemoryReaderImpl implements Reader {
    @Override
    public String read() {
        return "in-memory";
    }
}
~~~

Cả hai phương thức triển khai hợp lệ:

- `FileReaderImpl.read` khai báo `FileNotFoundException`, là lớp con của `IOException`.
- `MemoryReaderImpl.read` không khai báo checked exception nào; override được phép hẹp hơn hoặc loại bỏ ngoại lệ checked.
- Nếu thay khai báo của một override thành `throws Exception` hoặc `throws SQLException`, mã không hợp lệ với hợp đồng chỉ cho phép `IOException` ở interface `Reader`.
- Phương thức override vẫn có thể khai báo các unchecked exception mà không bị ràng buộc bởi danh sách checked exception của phương thức cha.

Một điểm thực dụng: kiểu tham chiếu tĩnh của biến quyết định **hợp đồng mà compiler dùng tại nơi gọi**. Dù đối tượng thực tế là `new MemoryReaderImpl()` không ném checked exception, đoạn `Reader r = new MemoryReaderImpl(); r.read();` vẫn được kiểm tra dựa trên chữ ký `Reader.read() throws IOException`.

Ví dụ:

~~~java
// Đoạn minh họa đặt trong một phương thức có import IOException.
Reader reader = new MemoryReaderImpl();
try {
    System.out.println(reader.read());
} catch (IOException ex) {
    System.out.println("Đọc thất bại");
}
~~~

Nếu thay kiểu biến thành `MemoryReaderImpl`, lời gọi `reader.read()` có chữ ký không khai báo checked exception, nên riêng lời gọi đó không còn tạo nghĩa vụ xử lý `IOException`.

## 9. Vị trí `throws` với generic method, varargs và abstract method

Mệnh đề `throws` luôn nằm **sau toàn bộ danh sách tham số**, kể cả khi phương thức có type parameters, varargs hoặc khai báo trong interface:

~~~java
import java.io.IOException;

class SyntaxExamples {
    public <T> T convert(T input) throws IOException {
        return input;
    }

    public void readAll(String... paths) throws IOException {
        for (String path : paths) {
            java.nio.file.Files.readString(java.nio.file.Path.of(path));
        }
    }
}

interface Operation {
    void run() throws IOException;
}
~~~

Các điểm dễ nhầm:

- `<T>` khai báo type parameter của phương thức. Nó đứng trước kiểu trả về; `throws` vẫn đứng sau dấu `)`.
- `String... paths` là varargs, vẫn nằm **bên trong** danh sách tham số.
- Chữ ký trong interface kết thúc bằng `;`; một phương thức có thân kết thúc phần khai báo `throws` rồi đến `{`.
- `throws` không nằm trong cặp ngoặc tham số, không nằm trong tên lớp ngoại lệ, và không dùng như annotation.

Java cũng hỗ trợ type variable trong `throws` theo các ràng buộc kiểu của Java; đây là trường hợp nâng cao. Khi viết API thông thường, khai báo các kiểu ngoại lệ cụ thể và có ý nghĩa vẫn dễ hiểu hơn.

## 10. Những giới hạn và lưu ý quan trọng

### 10.1. `throws` không yêu cầu một ngoại lệ phải thật sự được ném

Bạn có thể khai báo:

~~~java
// Mã minh họa trong một lớp.
static String version() throws java.io.IOException {
    return "1.0";
}
~~~

Dù đoạn hiện tại không ném `IOException`, cú pháp vẫn hợp lệ. Nhưng người gọi xét theo chữ ký đó vẫn có nghĩa vụ bắt hoặc khai báo checked exception khi biên dịch. Chỉ nên công bố ngoại lệ có ý nghĩa với hợp đồng hoặc khả năng mở rộng dự kiến; `throws` rộng một cách tùy tiện làm API bất tiện.

### 10.2. `throws` không được đặt vào một khối lệnh

Sai:

~~~java
// Minh họa không biên dịch.
static void work() {
    throws java.io.IOException;
}
~~~

Đúng: đặt `throws IOException` vào khai báo phương thức hoặc constructor. Trong phần thân, nếu cần ném, dùng `throw new IOException(...);`.

### 10.3. `throws` không xử lý hậu quả runtime

Ngay cả khi một phương thức khai báo `throws IOException`, thực thi chỉ chuyển sang đường lỗi **nếu thật sự có lời ném ngoại lệ** (do `throw` hay thao tác gọi phát sinh lỗi). Nếu không có `catch` phù hợp trên chuỗi lời gọi, ngoại lệ có thể thoát khỏi entry point và làm luồng kết thúc bất thường.

`throws` cũng không tự động ghi log, không rollback dữ liệu, không đóng tài nguyên, không biến checked exception thành unchecked và không tạo thông báo người dùng. Việc xử lý, dọn dẹp và quyết định khôi phục thuộc về cấu trúc điều khiển và thiết kế ở từng tầng.

### 10.4. `finally` và tài nguyên vẫn cần xử lý đúng

Khi phương thức/constructor khai báo `throws`, những tài nguyên đã được mở trước điểm thất bại cần được dọn dẹp an toàn; chỉ dùng `throws` không giải phóng chúng.

Trong I/O, ưu tiên `try-with-resources` để bảo đảm đóng `AutoCloseable` và bảo toàn thông tin lỗi phụ qua suppressed exceptions. Với đối tượng tạo dở do constructor ném ngoại lệ, Java không coi việc xây dựng đã thành công để trả đối tượng cho nơi gọi; constructor cần có trách nhiệm đối với tài nguyên mà nó đã cấp phát trước khi ném, vì nơi gọi chưa nắm được một tham chiếu hoàn chỉnh để đóng.

### 10.5. Quy tắc đối với constructor tĩnh, field initializer và initializer block

Không có khái niệm **static constructor** trong Java. Các static initializer không có danh sách tham số/chữ ký riêng để gắn `throws`; những quy tắc riêng về checked exception trong initializer không thể được giải quyết bằng cách viết `throws` sau `static { ... }`.

Trong instance initializer hoặc field initializer, ngoại lệ checked chịu quy tắc riêng gắn với các constructor có liên quan. Không nên cố đặt `throws` tại vị trí của field hoặc khối initializer; hãy xem xét thiết kế chuyển thao tác có thể lỗi vào constructor hoặc phương thức thích hợp và công bố ngoại lệ đúng vị trí.

## 11. Bảng lỗi cú pháp và biên dịch thường gặp

| Vấn đề | Vì sao lỗi hoặc bất tiện? | Cách sửa |
| --- | --- | --- |
| `void read() throw IOException` | Thiếu `s`: `throw` là câu lệnh, không phải khai báo danh sách lỗi. | Dùng `void read() throws IOException`. |
| `void read(throws IOException)` | `throws` sai vị trí trong cặp ngoặc tham số. | Đặt sau `)`: `read() throws IOException`. |
| `throws IOException | SQLException` | Dùng nhầm dấu `|` của multi-catch. | Phân cách bằng dấu phẩy. |
| Constructor khai báo `void ClassName()` | Trở thành method, không phải constructor. | Bỏ kiểu trả về. |
| Constructor lớp con gọi `super()` có checked exception nhưng không khai báo | Lời gọi constructor cha có thể để checked exception thoát. | Khai báo `throws` thích hợp ở constructor con hoặc thiết kế lại việc khởi tạo. |
| Phương thức gọi API khai báo `IOException` mà không bắt/khai báo | Compiler báo `unreported exception`. | Bắt đúng loại tại nơi xử lý được hoặc thêm `throws` hợp lý. |
| Override bổ sung `throws SQLException` khi interface chỉ có `IOException` | Vi phạm giới hạn checked exception của override. | Dùng loại checked nằm trong hợp đồng cha hoặc xử lý tại chỗ. |
| Ghi `throws Exception` ở mọi nơi | Che mờ loại thất bại, làm khó người gọi và khó giữ API ổn định. | Dùng kiểu cụ thể theo phạm vi trách nhiệm. |
| Chỉ ghi `throws IOException` rồi mong không cần dọn dẹp tài nguyên | Khai báo không thực hiện cleanup. | Dùng `try-with-resources`/`finally` đúng ngữ cảnh. |
| Ghi `throws RuntimeException` rồi tưởng người gọi buộc phải `catch` | Unchecked exception không thuộc yêu cầu catch-or-declare. | Hiểu đúng loại ngoại lệ; tài liệu hóa các lỗi quan trọng. |

## 12. Câu hỏi tự kiểm tra

1. **`throws` xuất hiện ở đâu trong chữ ký một phương thức?** — Sau dấu `)` của danh sách tham số, trước phần thân `{` hoặc dấu `;` của khai báo không có thân.
2. **Constructor có kiểu trả về không?** — Không. Khai báo `void ClassName()` tạo một phương thức có tên đó, không phải constructor.
3. **Nếu `A()` khai báo `throws IOException`, thì `new A()` ở phương thức gọi phải làm gì?** — Bắt `IOException` hoặc khai báo loại checked thích hợp tại phương thức gọi, trừ khi ngữ cảnh không thể phát sinh.
4. **Có thể viết `throws IOException, SQLException` không?** — Có. Danh sách phân tách bằng dấu phẩy.
5. **`throws IOException` có tự ném ngoại lệ không?** — Không. Đây chỉ là khai báo khả năng để lỗi thoát ra.
6. **Phương thức `throws IllegalArgumentException` có khiến `catch` trở thành bắt buộc không?** — Không. `IllegalArgumentException` là unchecked exception.
7. **Constructor lớp con phải làm gì khi `super()` khai báo `throws IOException`?** — Trên Java 17, constructor lớp con cần khai báo checked exception đó (hoặc kiểu cha phù hợp) nếu lời gọi có thể để nó thoát ra.
8. **Override một phương thức `throws IOException` có thể thêm `throws SQLException` không?** — Không, vì `SQLException` là checked exception khác nhánh, không nằm trong hợp đồng cha.
9. **`public static void main(String[] args) throws Exception` có hợp lệ không?** — Có. Nhưng ngoại lệ thoát khỏi `main` vẫn có thể khiến ứng dụng kết thúc bất thường.
10. **Một constructor chỉ trả về đối tượng hoàn chỉnh khi nào?** — Khi chuỗi khởi tạo thành công và constructor kết thúc bình thường; nếu ném ngoại lệ, thao tác tạo đối tượng không hoàn thành bình thường.

## Tài liệu tham khảo

- [Java Language Specification 17, §8.4.6 — Method Throws](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.6): cú pháp và quy tắc mệnh đề `throws` của phương thức.
- [Java Language Specification 17, §8.8.5 — Constructor Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.8.5): cú pháp constructor và khai báo ngoại lệ.
- [Java Language Specification 17, §8.8.7.1 — Explicit Constructor Invocations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.8.7.1): lời gọi `this(...)`, `super(...)` trong constructor.
- [Java Language Specification 17, §11.2 — Compile-Time Checking of Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.2): nghĩa vụ bắt hoặc khai báo checked exception.
- [Java Language Specification 17, §8.4.8.3 — Requirements in Overriding and Hiding](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.8.3): giới hạn checked exception khi override.
- [Java SE 17 API — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): ví dụ các phương thức I/O công bố `IOException`.

**Ghi nhớ:** với method viết `ReturnType name(params) throws ExceptionType { ... }`; với constructor viết `ClassName(params) throws ExceptionType { ... }` và **không có kiểu trả về**. `throws` công bố loại ngoại lệ có thể truyền ra; người gọi checked exception phải bắt hoặc khai báo, còn `throw` mới thực sự kích hoạt luồng ném ngoại lệ.
