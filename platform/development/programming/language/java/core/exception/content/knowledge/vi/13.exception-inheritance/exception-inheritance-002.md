# Không mở rộng tập checked exception được phép ném khi kế thừa và override trong Java

Khi một lớp con **override** phương thức của lớp cha, Java không cho phép nó tự ý khai báo thêm **checked exception mới hoặc rộng hơn** so với hợp đồng `throws` của phương thức được override. Quy tắc này còn áp dụng khi một lớp triển khai phương thức của interface, và khi một phương thức phải thỏa đồng thời nhiều hợp đồng thừa kế.

Ví dụ lớp cha:

~~~java
class Parent {
    void read() throws java.io.IOException {
        // Thao tác có thể lỗi I/O.
    }
}
~~~

Lớp con **được phép** thu hẹp xuống `FileNotFoundException` (lớp con của `IOException`), hoặc bỏ hoàn toàn khai báo checked exception:

~~~java
class Child extends Parent {
    @Override
    void read() throws java.io.FileNotFoundException {
        // Hợp lệ: FileNotFoundException extends IOException.
    }
}
~~~

Nhưng lớp con **không được phép** đổi sang `SQLException` hoặc mở rộng thành `Exception`:

~~~java
// KHÔNG BIÊN DỊCH với @Override.
class InvalidChild extends Parent {
    @Override
    void read() throws java.sql.SQLException {
        // SQLException không phải lớp con của IOException.
    }
}
~~~

Điểm cốt lõi: **phương thức override không được mở rộng tập kiểu checked exception mà caller có thể phải xử lý so với hợp đồng đã công bố qua lớp cha/interface**. Quy tắc này là ràng buộc *compile time*, không phải cơ chế runtime cấm phát sinh mọi loại ngoại lệ; **unchecked exception** (`RuntimeException` và `Error` cùng các lớp con) không bị hạn chế tương tự.

Bài học tập trung vào điều kiện hợp lệ của mệnh đề `throws` khi override, interface, nhiều interface và lời gọi qua kiểu cha; cách xử lý khi cần phát sinh lỗi checked mới; phân biệt với overload, constructor, unchecked exception và lý do thiết kế của Java. Các chương trình hoàn chỉnh chạy với Java 17+.

## 1. Nhắc lại checked và unchecked exception

Phân cấp liên quan:

~~~text
java.lang.Throwable
├── java.lang.Error                         unchecked
│   └── ...
└── java.lang.Exception
    ├── java.io.IOException                 checked
    │   ├── java.io.FileNotFoundException   checked
    │   └── java.io.EOFException            checked
    ├── java.sql.SQLException               checked
    └── java.lang.RuntimeException          unchecked
        ├── IllegalArgumentException       unchecked
        ├── IllegalStateException          unchecked
        └── ...
~~~

**Checked exception** gồm những loại `Throwable` không thuộc nhánh `RuntimeException` hoặc `Error`. Ví dụ `IOException`, `SQLException`, `FileNotFoundException`, `InterruptedException` là checked; `IllegalStateException` và `NullPointerException` là unchecked.

Với checked exception, compiler áp dụng quy tắc **catch-or-declare**: một phương thức có đường thực thi có thể ném checked exception thoát ra phải xử lý thích hợp hoặc khai báo được phép trong `throws`.

~~~java
import java.io.IOException;

// Minh họa trong một lớp.
static void read() throws IOException {
    throw new IOException("không đọc được");
}
~~~

Nếu caller không bắt `IOException`, chính phương thức chứa lời gọi có thể cần `throws IOException`. Đó là nghĩa vụ phát sinh từ **loại checked exception và đường thực thi**.

Khi override, còn một ràng buộc thứ hai: **chữ ký override phải tương thích với `throws` của phương thức cha**. Vì vậy không phải lúc nào chỉ cần thêm `throws SomeCheckedException` là có thể biên dịch.

## 2. Vì sao Java không cho mở rộng checked exception ở phương thức con?

Xét mã sử dụng qua kiểu lớp cha:

~~~java
class ReaderService {
    String load() throws java.io.IOException {
        return "data";
    }
}

class FileReaderService extends ReaderService {
    @Override
    String load() throws java.io.FileNotFoundException {
        return "file-data";
    }
}
~~~

Caller có thể viết:

~~~java
ReaderService service = new FileReaderService();
try {
    System.out.println(service.load());
} catch (java.io.IOException ex) {
    System.err.println(ex.getMessage());
}
~~~

**Kiểu tĩnh** của biến `service` là `ReaderService`, nên compiler kiểm tra lời gọi theo hợp đồng `ReaderService.load() throws IOException`. Khi chạy, phương thức thực tế có thể là `FileReaderService.load()` do dispatch động.

Nếu lớp con có thể tự khai báo một `SQLException` checked hoàn toàn không nằm trong hợp đồng cha, caller hợp lệ vừa viết ở trên sẽ **không bị compiler yêu cầu xử lý** lỗi SQL. Điều này phá vỡ bảo đảm catch-or-declare mà API lớp cha đã cung cấp.

Do đó Java yêu cầu phương thức con không mở rộng các checked exception được phép thoát ra qua chữ ký override.

**Ý nghĩa thiết kế:** đối tượng lớp con phải dùng được ở những vị trí trông đợi lớp cha, ít nhất đối với phần cam kết compile-time về các loại checked exception. Đây là một phần của hợp đồng thay thế (substitutability), nhưng không phải bảo đảm rằng mọi hành vi khác của lớp con đều đúng tự động.

## 3. Quy tắc ngắn gọn cho một lớp cha và một lớp con

Giả sử phương thức cha:

~~~java
public void execute() throws IOException;
~~~

Trong ví dụ này, `IOException` là checked exception đã công bố. Với override tương ứng:

| Khai báo trong lớp con | Hợp lệ? | Lý do |
| --- | --- | --- |
| `void execute()` | Có | Không công bố checked exception nào. |
| `void execute() throws FileNotFoundException` | Có | `FileNotFoundException` là lớp con của `IOException`. |
| `void execute() throws EOFException` | Có | `EOFException` là lớp con của `IOException`. |
| `void execute() throws IOException` | Có | Cùng kiểu checked với lớp cha. |
| `void execute() throws FileNotFoundException, EOFException` | Có | Mỗi loại đều được bao phủ bởi `IOException`. |
| `void execute() throws SQLException` | Không | `SQLException` không thuộc nhánh `IOException`. |
| `void execute() throws Exception` | Không | `Exception` rộng hơn `IOException`. |
| `void execute() throws Throwable` | Không | `Throwable` checked theo phân loại này và rộng hơn. |
| `void execute() throws IOException, SQLException` | Không | Có thêm `SQLException` mới, không được lớp cha cho phép. |
| `void execute() throws IllegalStateException` | Có | `IllegalStateException` unchecked. |
| `void execute() throws IOException, IllegalStateException` | Có | Checked phần `IOException` hợp lệ; unchecked không bị giới hạn tương tự. |

Bảng chỉ đánh giá **ràng buộc checked exception khi override**; code đầy đủ còn phải thỏa các điều kiện khác như visibility, return type, static/instance và khả năng truy cập của các kiểu.

Đặc biệt, `throws FileNotFoundException, EOFException` không phải “mở rộng” chỉ vì số lượng kiểu trong danh sách nhiều hơn. Vấn đề là **mỗi kiểu checked được khai báo có nằm trong vùng kiểu đã được hợp đồng cha bao phủ hay không**.

## 4. Thu hẹp, giữ nguyên hoặc bỏ `throws` checked

Một phương thức override có ba chiến lược thường gặp:

### 4.1. Giữ nguyên kiểu checked được phép

~~~java
// Đoạn minh họa trong lớp con của lớp có method load() throws IOException.
@Override
String load() throws java.io.IOException {
    return java.nio.file.Files.readString(path);
}
~~~

Cách này hợp lệ nếu lớp cha có hợp đồng tương ứng, `path` là biến `Path` và code khác thỏa điều kiện biên dịch.

### 4.2. Thu hẹp xuống subtype cụ thể

~~~java
// Đoạn minh họa trong một lớp con.
@Override
String load() throws java.io.FileNotFoundException {
    if (missing) {
        throw new java.io.FileNotFoundException("không thấy tệp");
    }
    return "OK";
}
~~~

Ở đây `missing` là điều kiện giả định. Cách thu hẹp làm hợp đồng của phương thức lớp con cụ thể hơn. Tuy nhiên nếu phần triển khai gọi một API có thể ném `IOException` chung, bạn vẫn phải xử lý loại lỗi rộng đó trong body, không thể dùng `throws FileNotFoundException` để công bố mọi `IOException`.

### 4.3. Bỏ khai báo checked exception

~~~java
// Đoạn minh họa một implementation đọc từ bộ nhớ.
@Override
String load() {
    return cachedValue;
}
~~~

Cách này hợp lệ nếu code trong body không làm thoát checked exception chưa được xử lý. Thực tế một implementation cache có thể không cần I/O nên không cần công bố `IOException`.

**Quy tắc cốt lõi:** lớp con có thể **làm ít lời hứa lỗi checked hơn** so với lớp cha (khai báo ít kiểu hơn hoặc kiểu con cụ thể hơn), nhưng không tự ý thêm một nhóm checked exception mà caller của lớp cha không được thông báo.

## 5. Chương trình Java 17+ hoàn chỉnh: override hợp lệ

Lưu tệp `OverrideCheckedDemo.java`:

~~~java
import java.io.FileNotFoundException;
import java.io.IOException;

public class OverrideCheckedDemo {
    static class Loader {
        String load(String name) throws IOException {
            throw new IOException("Lỗi đọc " + name);
        }
    }

    static final class LocalLoader extends Loader {
        @Override
        String load(String name) throws FileNotFoundException {
            if (!"known".equals(name)) {
                throw new FileNotFoundException("Thiếu " + name);
            }
            return "OK";
        }
    }

    static final class CachedLoader extends Loader {
        @Override
        String load(String name) {
            return "cache:" + name;
        }
    }

    public static void main(String[] args) {
        Loader first = new LocalLoader();
        try {
            first.load("missing");
        } catch (IOException ex) {
            System.out.println("Lỗi qua kiểu cha: " + ex.getClass().getSimpleName());
        }

        Loader second = new CachedLoader();
        try {
            System.out.println("Dữ liệu: " + second.load("x"));
        } catch (IOException ex) {
            System.out.println("Không chạy");
        }

        CachedLoader concrete = new CachedLoader();
        System.out.println("Trực tiếp: " + concrete.load("y"));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 OverrideCheckedDemo.java
java OverrideCheckedDemo
~~~

Stdout chính xác:

~~~text
Lỗi qua kiểu cha: FileNotFoundException
Dữ liệu: cache:x
Trực tiếp: cache:y
~~~

### Vì sao `main` có hai kiểu lời gọi khác nhau?

- `LocalLoader.load()` khai báo `FileNotFoundException` (checked subtype), hợp lệ vì `Loader.load()` đã khai báo `IOException`.
- `CachedLoader.load()` không công bố checked exception nào; đây là một cách **thu hẹp về tập ngoại lệ được khai báo** hoàn toàn hợp lệ.
- `first` có kiểu tĩnh `Loader`, nên lời gọi `first.load(...)` được kiểm tra theo `throws IOException` của `Loader.load`; `catch (IOException)` xử lý được `FileNotFoundException`.
- `second` cũng có kiểu tĩnh `Loader`, dù đối tượng thực sự là `CachedLoader`; compiler vẫn yêu cầu xử lý `IOException` khi gọi `second.load("x")` qua kiểu cha.
- Biến `concrete` có kiểu tĩnh `CachedLoader`, nên lời gọi `concrete.load("y")` **không cần `try/catch IOException`**, vì khai báo của chính `CachedLoader.load` không có checked exception.
- Việc `catch` ở `second` không chạy là đặc tính thực thi của ví dụ, không phải lý do compiler bỏ quy tắc checked exception khi gọi qua kiểu cha.

Đây là nơi cần phân biệt **kiểu tham chiếu tại compile time** với **implementation được chọn tại runtime**. Dynamic dispatch quyết định thân phương thức chạy; quy tắc kiểm tra checked exception ở lời gọi dựa trên chữ ký được phép theo kiểu tĩnh và ngữ cảnh.

## 6. Ví dụ sai: đổi `IOException` thành `SQLException`

Lưu tệp sau thành `InvalidOverride.java`. Nó được viết **cố ý sai để quan sát lỗi biên dịch**:

~~~java
import java.io.IOException;
import java.sql.SQLException;

class InvalidOverride {
    static class Parent {
        void execute() throws IOException { }
    }

    static class Child extends Parent {
        @Override
        void execute() throws SQLException { }
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 InvalidOverride.java
~~~

`javac` của JDK 17 có thông báo cốt lõi:

~~~text
execute() in Child cannot override execute() in Parent
overridden method does not throw SQLException
~~~

Đường dẫn, số dòng, cột báo lỗi và dấu con trỏ trong thông báo có thể khác nhau. Lý do không thay đổi: `SQLException` là checked exception **không được `Parent.execute()` cho phép**, vì nó không phải lớp con của `IOException`.

**Không có cách sửa bằng việc thêm `@Override` hoặc thay thứ tự trong mệnh đề `throws`.** Annotation `@Override` giúp compiler xác minh ý định override; nó không thay đổi hợp đồng ngoại lệ.

Nếu sửa lớp con thành:

~~~java
// Minh họa thay phần Child ở trên.
static class Child extends Parent {
    @Override
    void execute() throws java.io.FileNotFoundException { }
}
~~~

thì riêng ràng buộc checked exception sẽ hợp lệ. Nếu code thật sự cần thao tác cơ sở dữ liệu và có thể thất bại bằng `SQLException`, cần chọn một trong các cách xử lý ở mục tiếp theo.

## 7. Nếu implementation thực sự gọi API có thể ném checked exception mới thì sao?

Giả sử lớp cha định nghĩa:

~~~java
interface Processor {
    void process() throws java.io.IOException;
}
~~~

Implementation muốn gọi một thư viện cơ sở dữ liệu có thể ném `SQLException`:

~~~java
// KHÔNG HỢP LỆ nếu phương thức lớp con trực tiếp khai báo SQLException.
@Override
public void process() throws java.sql.SQLException {
    databaseOperation();
}
~~~

Đây chỉ là minh họa: `databaseOperation()` cần được định nghĩa, và nếu implementation có `SQLException` thoát ra, compiler sẽ từ chối vì interface không công bố loại đó.

Có một số hướng thiết kế, tùy trách nhiệm của tầng:

### 7.1. Bắt lỗi SQL và xử lý thật sự trong implementation

~~~java
@Override
public void process() throws java.io.IOException {
    try {
        databaseOperation();
    } catch (java.sql.SQLException ex) {
        recoverDatabaseOperation(ex);
    }
}
~~~

Đoạn trên phụ thuộc `databaseOperation()` và `recoverDatabaseOperation(...)`. Chỉ hợp lệ nếu `recoverDatabaseOperation` giải quyết đúng vấn đề, không để checked exception không tương thích thoát ra. **Không được nuốt lỗi** rồi giả vờ hoàn thành thành công nếu dữ liệu hoặc trạng thái đã không còn đúng.

### 7.2. Chuyển lỗi thành loại đã được hợp đồng cho phép, giữ cause

~~~java
@Override
public void process() throws java.io.IOException {
    try {
        databaseOperation();
    } catch (java.sql.SQLException ex) {
        throw new java.io.IOException("Không thể xử lý dữ liệu", ex);
    }
}
~~~

Về mặt kiểu, `IOException` được interface cho phép, nên ràng buộc compile-time hợp lệ. Nhưng cách mapping chỉ nên áp dụng nếu `IOException` **thật sự có ý nghĩa trong hợp đồng**. Không nên bọc mọi lỗi SQL thành “lỗi I/O” chỉ để qua compiler khi abstraction của API không xem đó là tình huống hợp lý.

### 7.3. Chuyển sang custom unchecked exception ở đúng abstraction

~~~java
@Override
public void process() {
    try {
        databaseOperation();
    } catch (java.sql.SQLException ex) {
        throw new ProcessingUnavailableException(
                "Không thể thực hiện thao tác", ex);
    }
}
~~~

Ví dụ này cần định nghĩa `ProcessingUnavailableException extends RuntimeException` với constructor nhận `(String, Throwable)`. Vì unchecked, nó không vi phạm giới hạn `throws` của override.

**Nhưng unchecked không tự động là cách tốt nhất.** Chuyển checked sang unchecked làm caller không còn bị compiler bắt xử lý; nếu lỗi thực sự cần được khôi phục bắt buộc, cần xem lại chính hợp đồng interface.

### 7.4. Sửa hợp đồng cha nếu bạn kiểm soát API

Nếu hợp đồng `Processor` được thiết kế cho cả I/O và SQL, có thể sửa để công bố một checked exception chung có nghĩa phù hợp với abstraction, hoặc định nghĩa một exception nghiệp vụ dùng làm hợp đồng chung. Thay đổi như vậy có thể buộc caller cũ sửa `catch`/`throws`; cần đánh giá khả năng tương thích trước khi sửa public API.

Không nên chỉ mở rộng `throws Exception` để tiện mọi implementation. Cách đó làm hợp đồng mơ hồ và đẩy nhiều nghĩa vụ xử lý không cần thiết lên caller.

## 8. Checked exception và unchecked exception có quy tắc khác nhau

Giới hạn `throws` khi override ở bài này **chỉ nhắm vào checked exception**. Một phương thức con có thể khai báo loại unchecked mới:

~~~java
class Parent {
    void execute() throws java.io.IOException { }
}

class Child extends Parent {
    @Override
    void execute() throws IllegalStateException {
        throw new IllegalStateException("không hợp lệ ở trạng thái hiện tại");
    }
}
~~~

Đây là đoạn minh họa hợp lệ xét ràng buộc `throws`: lớp con không khai báo checked exception mới, và `IllegalStateException` là unchecked.

Thậm chí nếu method cha không có `throws`:

~~~java
interface Greeter {
    String greet(String name);
}

class StrictGreeter implements Greeter {
    @Override
    public String greet(String name) throws IllegalArgumentException {
        if (name == null) {
            throw new IllegalArgumentException("name không được null");
        }
        return "Xin chào " + name;
    }
}
~~~

Java vẫn cho phép checked/unchecked policy như vậy, vì `IllegalArgumentException` là unchecked. Tuy nhiên **ngôn ngữ cho phép không có nghĩa hợp đồng hành vi luôn tốt**: implementation không nên tự ý tăng tiền điều kiện gây bất ngờ cho caller của interface.

Các lớp con `Error` cũng thuộc unchecked theo ngôn ngữ, nhưng **không nên dùng `Error` để biểu diễn lỗi nghiệp vụ thông thường**. Đừng hiểu “không bị kiểm tra khi override” là lời khuyên khai báo `throws Error` để giải quyết mọi ràng buộc.

## 9. Interface cũng là hợp đồng checked exception

Một interface có thể công bố:

~~~java
import java.io.IOException;

interface DataReader {
    String read() throws IOException;
}
~~~

Implementation:

~~~java
class InMemoryReader implements DataReader {
    @Override
    public String read() {
        return "memory";
    }
}
~~~

Hoàn toàn hợp lệ: implementation không ném checked exception, dù interface cho phép `IOException`.

Implementation khác:

~~~java
class FileDataReader implements DataReader {
    @Override
    public String read() throws java.io.FileNotFoundException {
        throw new java.io.FileNotFoundException("không thấy dữ liệu");
    }
}
~~~

Cũng hợp lệ: `FileNotFoundException` nằm trong họ `IOException`. Ngược lại, implementation không thể trực tiếp khai báo `throws SQLException` ở cùng phương thức vì interface không cho phép.

**Một phương thức trong interface có thể không có thân**, nhưng `throws` của nó vẫn là ràng buộc thật đối với những lớp triển khai. Nếu một interface có `default` method, lớp triển khai override default method vẫn phải tuân thủ hợp đồng checked exception của phương thức được override.

Java không buộc implementation phải liệt kê **y hệt** danh sách `throws` trong interface. Số lượng hoặc thứ tự kiểu không quan trọng bằng **quan hệ kiểu subtype** của checked exception đã công bố.

## 10. Khi một phương thức phải triển khai hai interface có hợp đồng khác nhau

Trường hợp nâng cao nhưng rất thực tế:

~~~java
import java.io.IOException;
import java.sql.SQLException;

interface TextFromFile {
    String load() throws IOException;
}

interface TextFromDatabase {
    String load() throws SQLException;
}
~~~

Một lớp có thể `implements TextFromFile, TextFromDatabase` nếu cung cấp **một implementation chung** của `load()`. Nhưng implementation đó phải thỏa **cả hai hợp đồng**.

Chương trình hoàn chỉnh `TwoInterfacesDemo.java`:

~~~java
import java.io.IOException;
import java.sql.SQLException;

public class TwoInterfacesDemo {
    interface TextFromFile {
        String load() throws IOException;
    }

    interface TextFromDatabase {
        String load() throws SQLException;
    }

    static class Combined implements TextFromFile, TextFromDatabase {
        @Override
        public String load() {
            return "kết quả chung";
        }
    }

    public static void main(String[] args) {
        Combined x = new Combined();
        System.out.println("Gọi implementation: " + x.load());

        TextFromFile fileView = x;
        try {
            System.out.println("Gọi interface: " + fileView.load());
        } catch (IOException ex) {
            System.out.println("Không chạy");
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 TwoInterfacesDemo.java
java TwoInterfacesDemo
~~~

Stdout chính xác:

~~~text
Gọi implementation: kết quả chung
Gọi interface: kết quả chung
~~~

### Vì sao phải bỏ `throws` checked ở implementation này?

`IOException` không phải subtype của `SQLException`, và `SQLException` cũng không phải subtype của `IOException`. Vì một method `Combined.load()` phải thỏa cả hai interface, nó **không thể tự công bố `throws IOException` hoặc `throws SQLException`**. Bỏ khai báo checked exception đáp ứng cả hai hợp đồng.

Mô hình:

~~~text
TextFromFile.load()       throws IOException
          \                    /
           \                  /
            Combined.load()  không khai báo checked
           /                  \
          /                    \
TextFromDatabase.load()   throws SQLException
~~~

Đây là ví dụ minh họa hai nhánh checked không có subtype chung phù hợp. Một implementation nói chung **có thể công bố một kiểu checked cụ thể nếu nó thỏa đồng thời tất cả hợp đồng** (ví dụ một subtype đặc biệt nếu hệ thống có phân cấp kiểu phù hợp). Không nên hiểu rằng mọi method triển khai nhiều interface đều bị cấm khai báo mọi checked exception.

**Khi gọi qua `fileView`**, compiler vẫn dùng chữ ký `TextFromFile.load() throws IOException`, nên `main` phải xử lý checked exception phù hợp, dù implementation thực tế `Combined.load()` không ném loại ấy. Khi gọi trực tiếp qua biến `Combined`, không cần `catch`.

## 11. Ví dụ sai khi kết hợp hai interface

Tệp `InvalidIntersection.java` dưới đây **cố ý không biên dịch**:

~~~java
import java.io.IOException;
import java.sql.SQLException;

class InvalidIntersection {
    interface A {
        void execute() throws IOException;
    }

    interface B {
        void execute() throws SQLException;
    }

    static class Both implements A, B {
        @Override
        public void execute() throws IOException { }
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 InvalidIntersection.java
~~~

Phần quan trọng của thông báo `javac` Java 17:

~~~text
execute() in Both cannot implement execute() in B
overridden method does not throw IOException
~~~

Lớp `Both` thỏa interface A về ngoại lệ, nhưng **không thỏa interface B**. Compiler kiểm tra mọi hợp đồng mà cùng một phương thức phải thực hiện, không chỉ hợp đồng bạn nghĩ đến đầu tiên.

Cách sửa đơn giản cho ví dụ không cần ngoại lệ checked là bỏ `throws IOException` khỏi `Both.execute()`. Nếu body có API thực sự ném `IOException`, cần xử lý nội bộ, bọc thành ngoại lệ phù hợp, hoặc thiết kế lại các interface một cách có chủ đích.

**Đừng sửa bằng `throws Exception`.** `Exception` còn rộng hơn cả `IOException` lẫn `SQLException`, không giải quyết ràng buộc nào của hai hợp đồng.

## 12. Những loại ngoại lệ checked được phép khi cha khai báo nhiều loại

Giả sử:

~~~java
class Parent {
    void operate() throws java.io.IOException, java.sql.SQLException {
        // ...
    }
}
~~~

Lớp con có thể khai báo:

~~~java
class Child extends Parent {
    @Override
    void operate() throws java.io.FileNotFoundException {
        // ...
    }
}
~~~

Vì `FileNotFoundException` là subtype của `IOException`, chỉ cần được **ít nhất một nhánh checked mà cha cho phép** bao phủ, miễn các hợp đồng override liên quan khác cũng được thỏa.

Cũng có thể giữ cả `IOException` và `SQLException`, hoặc chỉ `SQLException` nếu implementation phù hợp. Không bắt buộc lớp con phải khai báo đủ tất cả kiểu đã có trong cha.

Tuy nhiên:

~~~java
// Không hợp lệ nếu method cha chỉ cho IOException và SQLException.
@Override
void operate() throws java.text.ParseException {
    // ...
}
~~~

`ParseException` là checked exception khác, không thuộc `IOException` hoặc `SQLException`, nên không thể được bổ sung trong lời khai báo override.

Tóm lại, với một hợp đồng cha thông thường, **mỗi kiểu checked mà override liệt kê phải được một loại checked trong `throws` của cha bao phủ**. Với nhiều hợp đồng thừa kế, cần kiểm tra tương thích theo từng hợp đồng, không chỉ gộp danh sách `throws` của tất cả cha thành một tập cho phép tùy ý.

## 13. Một phương thức override không có `throws` có thể ném checked exception bên trong không?

**Có thể tạo hoặc nhận checked exception trong body**, nhưng nó **không thể để checked exception không tương thích thoát ra**. Ví dụ một implementation có thể bắt `IOException` hoàn toàn:

~~~java
import java.io.IOException;

// Minh họa nằm trong một lớp đã implements interface phù hợp.
@Override
public String load() {
    try {
        return readData();
    } catch (IOException ex) {
        return "giá trị dự phòng";
    }
}
~~~

Cần định nghĩa `readData()` với `throws IOException`; đoạn này không độc lập. Nếu trả dữ liệu dự phòng hợp lệ theo hợp đồng, implementation có thể kết thúc bình thường mà không cần `throws IOException`.

Ngược lại, đoạn sau không hợp lệ khi cha không công bố `IOException`:

~~~java
@Override
public String load() {
    throw new java.io.IOException("lỗi đọc"); // Lỗi biên dịch.
}
~~~

Thông báo thường liên quan **unreported exception IOException; must be caught or declared to be thrown**. Nhưng nếu bạn thêm `throws IOException` vào override trong khi cha/interface không cho phép, lại gặp **lỗi ràng buộc override**.

Hai yêu cầu compile-time tồn tại đồng thời:

1. **Body phải xử lý hoặc khai báo checked exception có thể thoát.**
2. **Mệnh đề `throws` của override không được mở rộng checked exception so với hợp đồng cha.**

Không thể “lách” hai yêu cầu này chỉ bằng sửa từ khóa mà không thay đổi cách xử lý hoặc thiết kế.

## 14. `throw` và `throws` khác nhau

`throw` là câu lệnh **ném một đối tượng Throwable thực tế**:

~~~java
throw new java.io.FileNotFoundException("missing");
~~~

`throws` trong chữ ký **khai báo loại ngoại lệ có thể truyền ra khỏi phương thức**:

~~~java
void read() throws java.io.IOException {
    throw new java.io.FileNotFoundException("missing");
}
~~~

Ở phương thức trên, kiểu thực tế được ném là `FileNotFoundException`; `throws IOException` là hợp lệ vì nó bao phủ kiểu con.

Trong ràng buộc override, compiler kiểm tra **loại checked được khai báo** và những ngoại lệ body có thể ném. Việc bạn chỉ ném `FileNotFoundException` ở một nhánh không cho phép khai báo rộng thành `throws Exception` nếu cha chỉ `throws IOException`.

**Khai báo rộng quá mức cũng có thể làm chương trình không biên dịch**, dù trong triển khai thực tế không hề có trường hợp ném loại rộng đó. Vì vậy hãy chọn danh sách `throws` phản ánh đúng hợp đồng và giới hạn được thừa kế.

## 15. Kế thừa constructor không giống override phương thức

Constructor **không được override như phương thức instance**. Lớp con có thể có constructor riêng khai báo checked exception cần thiết cho quá trình tạo đối tượng, nhưng khi gọi constructor cha phải tuân theo kiểm tra checked exception của lời gọi `super(...)`.

Ví dụ:

~~~java
import java.io.IOException;
import java.sql.SQLException;

class Parent {
    Parent() throws IOException {
        // ...
    }
}

class Child extends Parent {
    Child() throws IOException, SQLException {
        super();
        // Có thể có bước riêng cần SQLException.
    }
}
~~~

Đoạn này hợp lệ xét ràng buộc checked exception của constructor: `Child()` không “override `Parent()`”; nó là constructor độc lập của lớp con, khai báo cả `IOException` từ `super()` và `SQLException` riêng nếu phù hợp.

Điểm cần nhớ: **đừng mang nguyên quy tắc throws khi override method áp dụng lên constructor**. Constructor được kiểm tra theo các quy tắc gọi và khởi tạo, không phải theo quan hệ override cùng chữ ký.

## 16. Overload cũng không phải override

Xét:

~~~java
class Parent {
    void save(String value) throws java.io.IOException { }
}

class Child extends Parent {
    void save(int value) throws java.sql.SQLException { }
}
~~~

`Child.save(int)` là một phương thức **overload**, vì danh sách tham số khác với `Parent.save(String)`. Nó không override `save(String)`, nên không bị ràng buộc bởi `throws IOException` của phương thức kia.

Nhưng nếu đổi thành `Child.save(String) throws SQLException`, đó là ứng viên override đúng chữ ký và vi phạm quy tắc checked exception.

**Dùng `@Override` để kiểm tra ý định.** Nếu bạn vô tình đổi tên phương thức hoặc kiểu tham số làm nó thành overload, compiler sẽ báo khi annotation không trỏ đến một phương thức được override phù hợp. Điều này giúp tránh lỗi tinh vi khi tưởng đã thay thế logic lớp cha.

Tương tự, phương thức `static` tham gia **method hiding**, không phải dynamic override như instance method, nhưng Java vẫn có các ràng buộc tương thích của chữ ký, gồm checked exception, đối với những phương thức static có quan hệ hiding phù hợp. Không nên dùng `static` như một cách tránh hợp đồng.

## 17. Quy tắc override còn liên quan những thành phần nào?

`throws` chỉ là **một phần** của điều kiện override. Một phương thức con còn phải thỏa:

- **Chữ ký hợp lệ:** cùng tên và tham số theo các quy tắc override, gồm các trường hợp generic/subsignature được JLS xác định.
- **Return type tương thích:** Java hỗ trợ **covariant return type** trong những điều kiện phù hợp; quy tắc trả về không phải quy tắc checked exception.
- **Không thu hẹp visibility trái phép:** ví dụ không thể override `public` method bằng `private` method.
- **`final`:** phương thức instance `final` không thể bị override.
- **Static vs instance:** không thể tùy ý chuyển một phương thức instance thành static để override.
- **Các generic throws/type variables:** với kiểu tham số hóa và type variable, JLS có quy tắc chi tiết về substitution, erasure và khả năng phát sinh cảnh báo unchecked.

Trong bài cơ bản với `IOException`, `SQLException` và lớp con của chúng, nguyên tắc “checked exception không rộng hơn hợp đồng cha” là công cụ chủ đạo. Khi xây API generic phức tạp, đừng áp dụng một phép so sánh chuỗi tên kiểu đơn giản thay cho kiểm tra kiểu đầy đủ của JLS.

Có thể gặp mã legacy dùng raw types hoặc các quan hệ generic tạo **unchecked warning** về `throws`. Cảnh báo kiểu không đồng nghĩa Java cho phép một override tùy ý ném bất kỳ checked exception nào; cần xem đúng quy tắc từ JLS và sửa cấu trúc generic khi cần.

## 18. Khi gọi qua interface và lớp cụ thể, `catch` có thể khác

Chú ý:

~~~java
interface Service {
    void run() throws java.io.IOException;
}

class FastService implements Service {
    @Override
    public void run() {
        System.out.println("OK");
    }
}
~~~

Nếu code gọi:

~~~java
Service service = new FastService();
try {
    service.run();
} catch (java.io.IOException ex) {
    // Hợp lệ: kiểu Service công bố IOException.
}
~~~

compiler dùng `Service.run() throws IOException`, vì biến có kiểu tĩnh `Service`.

Nếu code gọi:

~~~java
FastService concrete = new FastService();
concrete.run(); // Không cần try/catch IOException.
~~~

compiler dùng `FastService.run()`, không khai báo checked exception. Đây là hành vi quan trọng khi API thiết kế để mọi implementation có thể cung cấp tính năng khác nhau, nhưng caller chung phải xử lý theo một hợp đồng nhất quán.

Không nên giải thích rằng compiler “kiểm tra class object thật tại runtime để biết ngoại lệ nào cần bắt”. Quy tắc checked exception là **kiểm tra tại compile time**, trong khi Java chọn implementation instance method tại runtime.

## 19. Không tự động mở rộng hợp đồng bằng đổi `throws` ở override

Đôi khi bạn muốn thêm một đường lỗi mới sau khi đổi implementation, ví dụ phiên bản sau chuyển từ đọc cache sang gọi database. Nếu method của interface đang có chữ ký:

~~~java
String find() throws java.io.IOException;
~~~

bạn **không thể chỉ sửa implementation** thành:

~~~java
@Override
public String find() throws java.sql.SQLException {
    // ...
}
~~~

Cách đó phá ràng buộc compile-time. Cần quyết định ở **ranh giới thiết kế API**:

1. Lỗi SQL có được xử lý/retry cục bộ ở implementation để không thoát ra không?
2. Có một loại ngoại lệ thuộc hợp đồng hiện có và hợp ngữ nghĩa để bọc lỗi SQL không?
3. API có nên được chỉnh sửa công khai để caller nhận một abstraction lỗi mới không?
4. Nếu thay đổi public checked exception, caller hiện tại và source compatibility bị ảnh hưởng ra sao?
5. Có cần chia nhỏ interface khi các implementation có hợp đồng lỗi khác nhau về căn bản không?

Với code thư viện, thêm `throws Exception` vào lớp cha không phải giải pháp mặc định vì ép mọi caller xử lý một loại quá rộng. Thay đổi hợp đồng cần tài liệu, test và kế hoạch nâng cấp rõ ràng.

## 20. Liên hệ với nguyên tắc thay thế và thiết kế API

Một lớp con dùng thay lớp cha có thể đảm bảo “không gây thêm những loại lỗi checked bắt buộc xử lý”. Điều này cho phép caller viết code dựa trên abstraction và compiler kiểm tra được nghĩa vụ ngoại lệ.

Tuy nhiên, quy tắc Java **không giải quyết toàn bộ vấn đề substitutability**:

- Lớp con vẫn có thể ném một unchecked exception mới và compiler chấp nhận.
- Lớp con có thể thay đổi kết quả, điều kiện đầu vào hoặc side effect theo cách làm hỏng kỳ vọng caller.
- Một method không khai báo checked exception vẫn có thể thất bại ở runtime do lỗi môi trường, bug hoặc logic.

Vì vậy khi thiết kế override, cần xem xét cả **hợp đồng ngữ nghĩa** bên cạnh `throws`: tiền điều kiện, hậu điều kiện, trạng thái sau thất bại và cách ứng dụng phục hồi.

Một subclass không nên dùng unchecked exception như công cụ để **lách có hệ thống** một checked exception mà caller thực sự cần xử lý. Nếu mọi implementation hợp lệ đều cần công bố lỗi mới, có thể vấn đề nằm ở thiết kế abstraction.

## 21. Các lỗi biên dịch thường gặp và cách sửa

| Lỗi hoặc hiểu nhầm | Vì sao xảy ra | Cách sửa |
| --- | --- | --- |
| Override `throws SQLException` trong khi cha chỉ `throws IOException` | Thêm checked exception ngoài hợp đồng cha | Bắt, bọc đúng abstraction, hoặc chỉnh thiết kế API |
| Override `throws Exception` khi cha chỉ `throws IOException` | Kiểu checked rộng hơn | Giữ `IOException` hoặc subtype thích hợp |
| Override `throws IOException` khi cha không có checked `throws` | Không có checked exception tương ứng được cho phép | Xử lý nội bộ hoặc chọn cơ chế lỗi khác đúng hợp đồng |
| Nghĩ cứ là lớp con thì được thêm loại checked bất kỳ | Phá hợp đồng caller dùng kiểu cha | Mỗi checked exception override phải được hợp đồng cho phép |
| Nghĩ bỏ `throws` đồng nghĩa body không thể dùng API checked | Body có thể gọi rồi bắt lỗi | Xử lý đầy đủ trước khi phương thức kết thúc |
| Hai interface khai báo checked khác nhau, implementation chọn một bên | Phải thỏa **cả hai**, không chỉ một | Bỏ/bắt checked nếu không có subtype chung hợp lệ |
| Caller qua kiểu cha không bắt IOException vì biết object thật là class cache | Compiler kiểm tra theo **kiểu tĩnh** của lời gọi | Bắt/khai báo theo hợp đồng của kiểu tĩnh |
| Nghĩ unchecked cũng phải là subtype của các checked trong cha | Unchecked không bị ràng buộc tương tự | Vẫn cần thiết kế ngữ nghĩa hợp lý |
| Sửa signature thành `throws RuntimeException` để qua compiler | Có thể che đường lỗi thực sự caller cần xử lý | Cân nhắc hợp đồng thay vì lách bằng unchecked |
| Nhầm `throw` với `throws` | Một bên ném đối tượng, một bên khai báo khả năng lỗi | Phân biệt statement và method declaration |
| Nhầm constructor kế thừa override | Constructor không phải phương thức override | Áp dụng quy tắc constructor riêng |
| Đổi tham số thành overload rồi tưởng đã override | Method khác chữ ký không thay thế method cũ | Dùng `@Override`, kiểm tra signature |
| Chỉ xử lý lỗi compiler bằng việc bỏ `throws` | Checked exception có thể vẫn thoát từ body | Sửa đường xử lý hoặc truyền lỗi hợp lệ |

## 22. Checklist trước khi khai báo `throws` cho một override

Khi kiểm tra một lớp con hoặc implementation, hãy thực hiện lần lượt:

1. **Xác định chính xác phương thức cha/interface được override**, không nhầm overload.
2. **Đọc danh sách checked exception đã công bố** ở từng phương thức cha liên quan.
3. **Phân loại từng loại được nêu ở `throws` của lớp con**: checked hay unchecked?
4. Với **mỗi checked exception lớp con**, kiểm tra nó có được các hợp đồng cha liên quan cho phép theo quan hệ subtype và quy tắc JLS không.
5. Nếu có nhiều interface, **kiểm tra từng hợp đồng**; đừng đơn giản hợp nhất danh sách.
6. Đọc **body thực tế** để xác định checked exception có thể thoát từ API được gọi hoặc `throw`.
7. Nếu có checked exception mới, quyết định xử lý/recover, bọc có cause hoặc thay đổi abstraction.
8. Kiểm tra **lời gọi qua kiểu cha** có được caller bắt/khai báo đúng không.
9. Giữ `@Override` để tránh nhầm chữ ký và kiểm tra visibility, static/instance, return type.
10. Biên dịch ít nhất một đường **thành công** và một đường **thất bại**; với API công khai, thêm test dùng biến kiểu interface/lớp cha.
11. Tài liệu hóa điều kiện `@throws` cần thiết; không dùng Javadoc để thay chữ ký checked exception bắt buộc.
12. Tránh bọc lỗi thành unchecked chỉ để lặng lẽ đổi nghĩa vụ caller.

## 23. Tự kiểm tra

**Câu 1.** Parent khai báo `void read() throws IOException`. Child có được khai báo `throws FileNotFoundException` không?

**Đáp án:** Có. `FileNotFoundException` là subtype checked của `IOException`.

**Câu 2.** Cùng parent đó, child khai báo `throws Exception` có hợp lệ không?

**Đáp án:** Không. `Exception` rộng hơn `IOException`.

**Câu 3.** Child bỏ hoàn toàn `throws` có hợp lệ không?

**Đáp án:** Có, nếu body không để checked exception chưa được xử lý thoát ra.

**Câu 4.** Child khai báo `throws IllegalStateException` khi parent không khai báo checked exception nào có hợp lệ không?

**Đáp án:** Có xét ràng buộc checked `throws`, vì `IllegalStateException` là unchecked.

**Câu 5.** Nếu biến có kiểu tĩnh Parent nhưng chứa object Child đã bỏ `throws IOException`, caller của `variable.read()` phải xử lý IOException theo kiểu nào?

**Đáp án:** Theo chữ ký Parent khi kiểm tra compile-time; caller vẫn phải bắt hoặc khai báo `IOException` nếu phương thức cha công bố loại đó.

**Câu 6.** Hai interface cùng có `load()`, interface A `throws IOException` còn B `throws SQLException`. Implementation không có checked `throws` có hợp lệ không?

**Đáp án:** Có, miễn body không để checked exception trái hợp đồng thoát ra và các quy tắc override khác thỏa.

**Câu 7.** Trong ví dụ hai interface trên, implementation khai báo `throws IOException` có hợp lệ không?

**Đáp án:** Không; nó không thỏa hợp đồng B vì `IOException` không là subtype của `SQLException`.

**Câu 8.** Nếu body override gọi API ném `SQLException` nhưng cha chỉ cho `IOException`, có thể bỏ `throws SQLException` rồi để exception tự thoát không?

**Đáp án:** Không. Checked exception phải được bắt hoặc công bố bằng một kiểu được phép; không thể để nó thoát không xử lý chỉ vì bỏ khai báo.

**Câu 9.** Quy tắc này áp dụng y hệt lên constructor của lớp con không?

**Đáp án:** Không. Constructor không override; nó có chữ ký và nghĩa vụ checked riêng khi gọi `super(...)` hoặc các thao tác trong constructor.

**Câu 10.** Nếu lớp con đặt một phương thức cùng tên nhưng khác tham số, có phải override không?

**Đáp án:** Thường là overload; `@Override` giúp compiler kiểm tra xem có thật là override hợp lệ không.

**Câu 11.** Tại sao không nên đổi mọi `SQLException` thành `IOException` chỉ để biên dịch?

**Đáp án:** Vì quan hệ kiểu ở ngôn ngữ không thay thế tính đúng đắn của abstraction; mapping sai sẽ làm caller hiểu nhầm bản chất lỗi. Chỉ bọc khi loại đích có nghĩa hợp đồng phù hợp, và cần giữ `cause`.

**Câu 12.** Một method của interface khai báo `throws Exception`. Implementation có được dùng `throws IOException` không?

**Đáp án:** Có, vì `IOException` là subtype checked của `Exception` (giả sử không có hợp đồng override khác chặt hơn).

## 24. Tài liệu đối chiếu

- [Java Language Specification 17 — §8.4.8.3, Requirements in Overriding and Hiding](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.8.3): giới hạn checked exception trong phương thức override/hide, cùng các điều kiện về return và chữ ký.
- [Java Language Specification 17 — §8.4.6, Method Throws](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.6): ý nghĩa của mệnh đề `throws` và phân loại exception.
- [Java Language Specification 17 — §9.4.1, Inheritance and Overriding](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.4.1): quan hệ phương thức của interface và các quy tắc kế thừa.
- [Java Language Specification 17 — §11.2, Compile-Time Checking of Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.2): catch-or-declare và ngoại lệ có thể phát sinh từ body.
- [Java SE 17 API — `IOException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/IOException.html) và [`FileNotFoundException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/FileNotFoundException.html): đối chiếu quan hệ subtype.
- [Java SE 17 API — `SQLException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/SQLException.html): checked exception ở nhánh khác với `IOException`.

**Kết luận:** khi một phương thức **override** phương thức cha/interface, danh sách `throws` của nó không được công bố checked exception mới hoặc rộng hơn ngoài hợp đồng được kế thừa. Bạn có thể **thu hẹp, giữ nguyên hoặc bỏ** các checked exception được phép; unchecked exception không bị giới hạn tương tự. Nếu implementation cần phát sinh checked exception khác, hãy **xử lý, bọc đúng abstraction với cause, hoặc xem lại hợp đồng API**, thay vì chỉ sửa chữ ký để qua compiler.
