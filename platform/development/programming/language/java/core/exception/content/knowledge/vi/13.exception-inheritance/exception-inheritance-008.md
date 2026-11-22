# Checked exception trong instance initializer và các constructor của Java

Trong Java, một đối tượng có thể thực hiện việc khởi tạo **trước khi thân constructor của lớp đó chạy**: các biểu thức khởi tạo instance field và các **instance initializer block** (`{ ... }` ở cấp lớp). Nếu những đoạn khởi tạo này có thể ném **checked exception**, Java áp dụng một quy tắc đặc biệt: đối với **lớp có tên (named class)**, phải có ít nhất một constructor được khai báo tường minh, và **tất cả constructor được khai báo tường minh của lớp** phải có mệnh đề `throws` bao phủ các checked exception có thể phát sinh từ instance initializer. Riêng **anonymous class** có cơ chế ngoại lệ đặc biệt vì lập trình viên không thể tự khai báo constructor của anonymous class.

Quy tắc dễ bị bỏ sót:

~~~java
import java.io.IOException;

class Config {
    String data = read(); // read() throws IOException.

    Config() throws IOException {
        // Hợp lệ nếu read() đã được định nghĩa phù hợp.
    }

    static String read() throws IOException {
        throw new IOException("không đọc được");
    }
}
~~~

Với lớp trên, lỗi `IOException` có thể được ném **trong quá trình tạo `new Config()`**, trước thân `Config()`. Vì thế constructor phải công bố nó, để caller của `new Config()` có thể `catch` hoặc `throws` theo quy tắc checked exception.

Bài này trình bày đầy đủ quan hệ giữa **instance field initializer, instance initializer block, constructor, constructor chaining và caller**; phân biệt với **static initializer**, giải thích trường hợp **nhiều constructor**, **constructor mặc định**, **anonymous class**, thứ tự chạy và xử lý thất bại khi khởi tạo. Các chương trình chạy được đã được kiểm tra với mức ngôn ngữ Java 17.

## 1. Bốn vị trí mã dễ bị nhầm là cùng một constructor

Xét một lớp đơn giản:

~~~java
class Profile {
    // 1. Instance field initializer:
    String name = loadName();

    // 2. Instance initializer block:
    {
        verifyProfile();
    }

    // 3. Constructor body:
    Profile() {
        System.out.println("Constructor body");
    }

    // 4. Static initializer block:
    static {
        System.out.println("Class initialization");
    }

    static String loadName() {
        return "guest";
    }

    void verifyProfile() {
        // Kiểm tra trạng thái.
    }
}
~~~

Đây là **lớp minh họa**, có thể biên dịch khi được đặt trong tệp Java phù hợp. Bốn thành phần làm những việc khác nhau:

| Thành phần | Thời điểm/đối tượng | Có thể nằm trong đường khởi tạo mỗi instance? |
| --- | --- | --- |
| Instance field initializer: `String name = loadName()` | Khởi tạo field trên mỗi đối tượng, theo thứ tự văn bản tương ứng | Có |
| Instance initializer block: `{ verifyProfile(); }` | Chạy khi khởi tạo từng instance, xen kẽ theo thứ tự văn bản với instance field initializers | Có |
| Constructor body: `Profile() { ... }` | Thực hiện phần thân constructor được gọi, sau giai đoạn khởi tạo instance của lớp đó, trừ trường hợp chuyển tiếp `this(...)` được giải thích sau | Có |
| Static initializer: `static { ... }` | Khởi tạo **class**, không phải chạy mỗi khi tạo đối tượng | Không, bản chất khác |

Một lớp có thể có nhiều instance initializer block, nhiều instance field có initializer, và nhiều constructor overload. Đối với một lượt khởi tạo instance bình thường, **các instance field initializer và instance initializer block của cùng lớp chạy theo thứ tự xuất hiện trong mã nguồn**.

Nếu đoạn ở cấp instance có thể ném một checked exception, trách nhiệm công bố nó không nằm ở “chữ ký của block” (block không có chữ ký), mà được kiểm tra thông qua **toàn bộ constructor của named class** theo JLS §11.2.3.

## 2. Checked exception và quy tắc catch-or-declare

Checked exception là các loại `Throwable` **không** thuộc nhánh `RuntimeException` hoặc `Error`. Các kiểu thường gặp:

- `IOException`, `FileNotFoundException`: lỗi I/O có thể cần được caller xử lý.
- `SQLException`: lỗi khi truy cập qua API cơ sở dữ liệu.
- `ClassNotFoundException`: không tìm thấy lớp trong một cơ chế nạp lớp.
- `InterruptedException`: thao tác bị gián đoạn.
- Các lớp do ứng dụng định nghĩa `extends Exception` mà không thuộc `RuntimeException`.

Ngược lại, `IllegalStateException`, `IllegalArgumentException`, `NullPointerException`, `Error` và các lớp con của nhánh unchecked **không bị compiler yêu cầu bắt hoặc khai báo** theo cùng quy tắc.

Đối với constructor:

~~~java
import java.io.IOException;

class Client {
    Client() throws IOException {
        if (System.currentTimeMillis() < 0) {
            throw new IOException("lỗi khởi tạo");
        }
    }
}
~~~

`Client()` được phép công bố checked exception trong `throws`. Khi caller viết:

~~~java
try {
    Client client = new Client();
    System.out.println("Tạo thành công");
} catch (IOException ex) {
    System.out.println("Không tạo được: " + ex.getMessage());
}
~~~

compiler có thể xác minh caller đã xử lý loại checked mà constructor cho phép truyền ra. Điều đó đúng **dù lỗi xuất hiện trong thân constructor, trong lời gọi `super(...)`, trong lời gọi `this(...)` hay trong instance initializer được thực hiện khi tạo đối tượng**.

Không được hiểu `throws IOException` là lệnh phát sinh lỗi. `throws` chỉ **công bố khả năng checked exception thoát ra**, còn `throw` hoặc lời gọi một API thất bại mới thực sự tạo đường thực thi bất thường.

## 3. Quy tắc đặc biệt của named class theo JLS §11.2.3

Nếu một **instance variable initializer** hoặc **instance initializer block** của **named class** *có thể ném* checked exception loại E theo phân tích compile time, Java yêu cầu đồng thời:

1. Named class có **ít nhất một constructor được khai báo tường minh** trong mã nguồn.
2. **Mỗi constructor được khai báo tường minh** của named class có mệnh đề `throws` ghi rõ E **hoặc một superclass bao phủ E**.
3. Các đường thực thi trong phần thân constructor cũng thỏa quy tắc checked exception thông thường; gọi `super(...)` và `this(...)` không miễn trừ điều này.

Ví dụ với E = `FileNotFoundException`:

~~~java
import java.io.FileNotFoundException;
import java.io.IOException;

class Document {
    String content = load();

    Document() throws IOException { }             // Bao phủ E.
    Document(int id) throws FileNotFoundException { } // Chính E.

    static String load() throws FileNotFoundException {
        throw new FileNotFoundException("thiếu tài liệu");
    }
}
~~~

Ở đây cả hai constructor đều công bố được `FileNotFoundException`, trực tiếp hoặc bằng superclass `IOException`. Xét riêng quy tắc checked exception trong initializer, ví dụ này hợp lệ.

**Không nhất thiết mọi constructor phải khai báo đúng cùng một chuỗi `throws IOException`.** Điều kiện là **mỗi checked exception có thể thoát từ initializer được một kiểu trong `throws` của từng constructor bao phủ**.

Nếu initializer có thể phát sinh `IOException` **và** `SQLException`, mọi constructor cần công bố cả hai loại hoặc những superclass phù hợp bao phủ chúng. Có thể viết `throws Exception`, nhưng với public API việc khai báo quá rộng thường làm caller khó xác định chiến lược xử lý.

### Một constructor thiếu `throws` làm cả lớp không hợp lệ

~~~java
import java.io.IOException;

// CỐ Ý SAI:
class OneMissingThrowsBad {
    String value = fetch();

    OneMissingThrowsBad() throws IOException { }
    OneMissingThrowsBad(int mode) { } // Không công bố IOException.

    static String fetch() throws IOException {
        throw new IOException();
    }
}
~~~

Dù constructor không tham số đã công bố `IOException`, constructor nhận `int` vẫn không thỏa quy tắc. Thậm chí nếu lập trình viên định “chỉ dùng constructor đầu”, **compiler vẫn kiểm tra tất cả constructor đã khai báo**.

Chạy `javac OneMissingThrowsBad.java` sẽ thất bại với lỗi checked exception chưa được bắt/khai báo; cách trình bày vị trí lỗi có thể trỏ vào `fetch()` trong initializer.

## 4. Tại sao constructor mặc định không đủ?

Nếu một named class **không viết bất kỳ constructor nào**, Java có thể cung cấp một **default constructor** theo quy tắc ngôn ngữ. Nhưng default constructor này **không thể được lập trình viên gắn một mệnh đề `throws IOException` vào chính khai báo ngầm**.

Vì vậy:

~~~java
import java.io.IOException;

// CỐ Ý SAI:
class NoConstructorBad {
    String value = fetch(); // Có thể ném checked IOException.

    static String fetch() throws IOException {
        throw new IOException();
    }
}
~~~

là lỗi biên dịch. Không thể giải quyết bằng cách trông cậy vào constructor mặc định.

Một cách sửa:

~~~java
import java.io.IOException;

class HasConstructor {
    String value = fetch();

    HasConstructor() throws IOException { }

    static String fetch() throws IOException {
        return "ready";
    }
}
~~~

Khi gọi `new HasConstructor()`, caller phải xử lý hoặc khai báo `IOException` theo chữ ký constructor, mặc dù `fetch()` trong ví dụ sửa luôn trả giá trị ổn định khi chạy. Compiler áp dụng phân tích khả năng ném dựa trên chữ ký `fetch() throws IOException`, không chứng minh mọi nhánh runtime bên trong phương thức đó sẽ luôn thành công.

**Cách sửa khác:** xử lý checked exception ngay trong initializer bằng `try/catch`, nếu có một giá trị dự phòng hay đường khôi phục hợp lệ. Khi checked exception không còn có thể thoát khỏi initializer, không nhất thiết phải thêm `throws` cho constructor chỉ vì initializer ấy.

## 5. `instance initializer` không được khai báo `throws` riêng

Block cấp instance là một phần của class body:

~~~java
import java.io.IOException;

class Example {
    {
        initialize();
    }

    Example() throws IOException { }

    static void initialize() throws IOException {
        // Có thể ném IOException.
    }
}
~~~

Đoạn trên hợp lệ vì constructor khai báo `throws IOException`. Không tồn tại cú pháp Java hợp lệ kiểu:

~~~java
// CỐ Ý SAI: instance initializer block không có chữ ký throws.
{
    throws IOException;
    initialize();
}
~~~

Bạn không thể gắn `throws` vào header của initializer block; đó không phải phương thức hoặc constructor. Vì vậy nơi công bố checked exception là các constructor, còn nơi **xử lý ngay** checked exception có thể là `try/catch` bên trong block.

Lưu ý khác: một instance initializer block của Java phải **có khả năng hoàn tất bình thường**, theo quy tắc riêng về khả năng đến được cuối block. Viết một block chỉ có `throw new IOException(...);` vô điều kiện làm nó không thể hoàn tất bình thường; lỗi này **khác** với lỗi thiếu `throws` ở constructor. Nếu muốn tạo đường thất bại có điều kiện, sử dụng câu lệnh điều kiện hoặc phương thức có thể ném, như những ví dụ chạy được bên dưới.

## 6. Thứ tự thực thi: superclass, instance initializers, constructor body

Khi tạo một đối tượng của named class thông thường, luồng khởi tạo cần được hiểu theo các tầng, không đơn giản là “constructor chạy trước mọi initializer”.

Một mô hình thường gặp:

~~~text
new Child(...)
    │
    ├─ Đánh giá các argument và vào constructor liên quan
    ├─ Gọi constructor khác theo chuỗi this(...) / super(...)
    ├─ Hoàn thành khởi tạo superclass phù hợp
    ├─ Thực hiện instance field initializers và instance initializer
    │  blocks của Child theo thứ tự văn bản
    └─ Thực hiện các câu lệnh còn lại trong thân constructor của Child
~~~

**Chi tiết:** Java cũng có những bước cấp phát, gán mặc định field, xử lý constructor invocation và quy tắc về outer instance. Sơ đồ trên chỉ nhấn vào phần quan trọng cho bài học: **instance initializer của một lớp được chạy trước phần thân thực hiện chính của constructor lớp đó, sau khi constructor cấp trên và các lời gọi chuyển tiếp liên quan đã được thực hiện đúng quy tắc**.

Nếu một instance field initializer ném `IOException`:

- Các initializer phía sau của lớp đó **không chạy**.
- Phần thân constructor của lớp đó **không chạy**.
- Đường tạo `new Child(...)` kết thúc bất thường; caller có thể bắt checked exception.
- Những side effect đã xảy ra trước điểm ném **không tự được rollback**.
- Đối tượng chưa được tạo thành công không được trả về từ biểu thức `new`.

Đừng nhầm ngoại lệ khi khởi tạo instance với thất bại của **static class initialization**; chúng có quy tắc kiểm tra và cách báo lỗi khác nhau.

## 7. Chương trình Java 17 hoàn chỉnh: lỗi ở field và block trước thân constructor

Tệp `NamedInitializerDemo.java`:

~~~java
import java.io.IOException;

public class NamedInitializerDemo {
    static boolean failField;
    static boolean failBlock;
    final String value = loadField();

    static String loadField() throws IOException {
        System.out.println("Khởi tạo field");
        if (failField) throw new IOException("field lỗi");
        return "ready";
    }

    {
        System.out.println("Khối khởi tạo");
        if (failBlock) throw new IOException("block lỗi");
    }

    NamedInitializerDemo() throws IOException {
        System.out.println("Thân constructor rỗng");
    }

    NamedInitializerDemo(String label) throws IOException {
        this();
        System.out.println("Thân constructor có tham số: " + label);
    }

    public static void main(String[] args) {
        try {
            System.out.println("Giá trị: " + new NamedInitializerDemo("A").value);
        } catch (IOException ex) {
            System.out.println("Lỗi: " + ex.getMessage());
        }

        failField = true;
        try {
            new NamedInitializerDemo();
        } catch (IOException ex) {
            System.out.println("Lỗi: " + ex.getMessage());
        }

        failField = false;
        failBlock = true;
        try {
            new NamedInitializerDemo();
        } catch (IOException ex) {
            System.out.println("Lỗi: " + ex.getMessage());
        }
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 NamedInitializerDemo.java
java NamedInitializerDemo
~~~

**Stdout chính xác:**

~~~text
Khởi tạo field
Khối khởi tạo
Thân constructor rỗng
Thân constructor có tham số: A
Giá trị: ready
Khởi tạo field
Lỗi: field lỗi
Khởi tạo field
Khối khởi tạo
Lỗi: block lỗi
~~~

### Phân tích ba lượt tạo đối tượng

**Lượt 1 — thành công:** `failField=false`, `failBlock=false`.

1. `value = loadField()` chạy và in `Khởi tạo field`.
2. Instance initializer block in `Khối khởi tạo`.
3. Constructor `NamedInitializerDemo()` được gọi qua `this()` và in `Thân constructor rỗng`.
4. Phần còn lại của `NamedInitializerDemo(String)` in `Thân constructor có tham số: A`.
5. Biểu thức `new ...` hoàn tất; caller đọc `value` là `ready`.

**Lượt 2 — lỗi field initializer:** `failField=true`.

1. `loadField()` in `Khởi tạo field` rồi ném checked `IOException("field lỗi")`.
2. Block phía sau không chạy, và không có dòng nào từ thân constructor.
3. Caller bắt `IOException` và in `Lỗi: field lỗi`.

**Lượt 3 — lỗi instance initializer block:** `failField=false`, `failBlock=true`.

1. Field initializer hoàn tất bình thường.
2. Block in `Khối khởi tạo` rồi ném `IOException("block lỗi")`.
3. Thân constructor không chạy; caller bắt và in `Lỗi: block lỗi`.

Cả hai constructor của named class đều khai báo `throws IOException`. Đó là điều kiện để compiler chấp nhận các checked exception có thể phát sinh từ cả field initializer và block.

### Tác động của `this()` đối với lượt khởi tạo

Constructor nhận `String` dùng `this()` để chuyển tới constructor không tham số. Chuỗi gọi constructor **không khiến instance field initializers và instance initializer block của cùng đối tượng chạy hai lần**. Chúng được thực hiện một lượt trong quá trình khởi tạo lớp đó, trước khi các phần thân constructor hoàn tất theo thứ tự chuyển tiếp.

Vì constructor `NamedInitializerDemo(String)` gọi `this()`, nó cũng có đường nhận `IOException` từ constructor đích. Do đó cả chính sách **khai báo ở mọi constructor vì initializer** lẫn nghĩa vụ **xử lý/khai báo checked exception từ lời gọi `this()`** đều cần được tuân thủ.

## 8. Kiểm tra nhiều constructor và constructor chaining

Nếu chỉ có một constructor, quy tắc đơn giản:

~~~java
class Single {
    String data = load();

    Single() throws java.io.IOException { }

    static String load() throws java.io.IOException {
        return "OK";
    }
}
~~~

Với hai constructor overload:

~~~java
class Multiple {
    String data = load();

    Multiple() throws java.io.IOException { }

    Multiple(int mode) throws java.io.IOException {
        this();
        // Tiếp tục sau khi constructor đích hoàn tất.
    }

    static String load() throws java.io.IOException {
        return "OK";
    }
}
~~~

Cả hai đều khai báo `IOException`. Nếu `Multiple(int)` không khai báo, compiler vẫn có thể báo lỗi **từ initializer** và/hoặc **lời gọi `this()`**. Không được cho rằng constructor chuyển tiếp không cần `throws` vì toàn bộ code khởi tạo đã “nằm trong constructor khác”.

Một lớp có thể dùng cả constructor gọi `super(...)` và một constructor gọi `this(...)`. **Mỗi constructor** của named class có initializer có thể ném checked exception vẫn phải đáp ứng điều kiện khai báo của JLS.

Nếu superclass constructor cũng công bố một checked exception khác, constructor lớp con còn phải xử lý hoặc khai báo **các loại checked thoát từ `super(...)`**. Trách nhiệm đó là quy tắc constructor invocation thông thường, ngoài quy tắc riêng cho initializer của lớp con.

## 9. Caller của `new` chịu hợp đồng constructor

Giả sử:

~~~java
class DocumentReader {
    String content = openDocument();

    DocumentReader() throws java.io.IOException { }

    static String openDocument() throws java.io.IOException {
        return "text";
    }
}
~~~

Caller:

~~~java
try {
    DocumentReader reader = new DocumentReader();
    System.out.println(reader.content);
} catch (java.io.IOException ex) {
    System.err.println("Không tạo được reader: " + ex.getMessage());
}
~~~

`IOException` có thể được truyền tới caller từ **instance initializer**, dù constructor rỗng. Đây là lý do chữ ký constructor không chỉ mô tả các câu lệnh **viết trực tiếp bên trong dấu ngoặc nhọn constructor**. Nó còn mô tả những lỗi checked có thể phát sinh khi **hoàn tất thao tác tạo đối tượng**.

Nếu caller không bắt và không có `throws IOException` thích hợp, compiler báo lỗi. Bản thân `new DocumentReader()` là một **class instance creation expression** có thể ném checked exception từ constructor đã chọn.

Khi thư viện thay đổi và bắt đầu tạo thêm tài nguyên trong instance field initializer, việc bổ sung checked exception vào constructor public có thể ảnh hưởng **source compatibility** của client. Do đó không nên chuyển tùy tiện một thao tác I/O có thể thất bại vào instance initializer mà chưa xem xét hợp đồng tạo đối tượng.

## 10. Cách sửa khi không muốn constructor khai báo checked exception

Có thể **xử lý lỗi ngay trong initializer**, với đường khôi phục thật sự hợp lệ. Đây không phải “né compiler” bằng cách bỏ lỗi; phải quyết định trạng thái thay thế có an toàn hay không.

Chương trình `HandledInitializerDemo.java`:

~~~java
import java.io.IOException;

public class HandledInitializerDemo {
    final String state;

    static String fetch() throws IOException {
        throw new IOException("nguồn không sẵn");
    }

    {
        String result;
        try {
            result = fetch();
        } catch (IOException ex) {
            System.out.println("Đã xử lý: " + ex.getMessage());
            result = "fallback";
        }
        state = result;
    }

    HandledInitializerDemo() {
        System.out.println("Constructor: " + state);
    }

    public static void main(String[] args) {
        System.out.println("Kết quả: " + new HandledInitializerDemo().state);
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 HandledInitializerDemo.java
java HandledInitializerDemo
~~~

Stdout:

~~~text
Đã xử lý: nguồn không sẵn
Constructor: fallback
Kết quả: fallback
~~~

Ở đây `fetch()` ném checked `IOException`, nhưng `try/catch` trong instance initializer **bắt và giải quyết nó bằng giá trị dự phòng**. Vì initializer không còn để `IOException` thoát ra, constructor `HandledInitializerDemo()` không cần `throws IOException` chỉ vì `fetch()`.

**Lưu ý:** ví dụ giả định chuỗi `"fallback"` là trạng thái hợp lệ. Trong ứng dụng thực, nếu không thể hoạt động thiếu dữ liệu khởi tạo, không nên nuốt `IOException` rồi tạo một đối tượng trông như thành công. Khi không có đường phục hồi, hãy giữ nguyên checked exception hoặc bọc nó thành một exception có ý nghĩa đúng với hợp đồng.

## 11. Có nên chuyển checked exception thành unchecked exception trong initializer?

Đôi khi một API không muốn để public constructor công bố checked exception mà chọn bọc lỗi bằng unchecked exception:

~~~java
class ConfigurationUnavailableException extends RuntimeException {
    ConfigurationUnavailableException(String message, Throwable cause) {
        super(message, cause);
    }
}

class Configuration {
    final String content;

    {
        String value;
        try {
            value = readConfiguration();
        } catch (java.io.IOException ex) {
            throw new ConfigurationUnavailableException(
                    "Không khởi tạo được cấu hình", ex);
        }
        content = value;
    }

    Configuration() { }

    static String readConfiguration() throws java.io.IOException {
        return "mode=prod";
    }
}
~~~

Đây là **mã minh họa gồm các lớp tương ứng**, hợp lệ với các điều kiện biên dịch thông thường. Khi phát sinh `IOException`, initializer bọc lỗi thành `ConfigurationUnavailableException` (**unchecked**) và constructor không cần công bố `throws IOException`.

Tuy nhiên, đây là quyết định **thiết kế hợp đồng**, không phải cách sửa luôn luôn đúng:

- Caller không còn bị compiler buộc xử lý lỗi khởi tạo.
- Loại exception được ném ra cần biểu đạt đúng abstraction và tình huống thất bại.
- **Cause** cần được giữ qua `super(message, cause)` để không mất `IOException` ban đầu.
- Nếu việc tạo đối tượng có thể thất bại ở đường dự kiến và caller bắt buộc phục hồi, checked exception hoặc **factory method** có thể phù hợp hơn.

Có thể chuyển logic I/O ra khỏi initializer sang **factory method** có `throws IOException`, rồi chỉ tạo đối tượng sau khi các bước dễ thất bại đã thành công. Cách này thường cho phép quản lý tài nguyên và trạng thái khởi tạo rõ ràng hơn.

## 12. Khác biệt với constructor body thông thường

Một constructor body có thể trực tiếp ném checked exception:

~~~java
import java.io.IOException;

class Parser {
    Parser() throws IOException {
        if (System.nanoTime() < 0) {
            throw new IOException("khởi tạo thất bại");
        }
    }
}
~~~

Với trường hợp này, nghĩa vụ `throws IOException` phát sinh **từ phần thân constructor**. Không bắt buộc lớp phải có initializer nào.

Nếu bỏ `throws IOException` mà vẫn ném:

~~~java
import java.io.IOException;

// CỐ Ý SAI:
class ConstructorBodyBad {
    ConstructorBodyBad() {
        throw new IOException("body");
    }
}
~~~

sẽ là lỗi compile time: checked exception chưa được bắt hoặc khai báo.

Vậy có hai ngữ cảnh liên quan nhưng khác nhau:

| Điểm có thể ném checked exception | Quy tắc bắt buộc |
| --- | --- |
| Phần thân constructor | Constructor đó phải bắt hoặc khai báo kiểu được phép thoát |
| Lời gọi `super(...)` hoặc `this(...)` | Constructor chứa lời gọi phải tuân thủ catch-or-declare theo quy tắc constructor invocation |
| Instance field initializer của named class | **Phải có explicit constructor; mọi explicit constructor** phải khai báo checked exception có thể thoát khỏi initializer |
| Instance initializer block của named class | Cùng quy tắc như instance field initializer |
| Instance initializer đã tự bắt và xử lý hết checked exception | Không còn checked exception đó thoát ra, không cần khai báo nó chỉ vì có lời gọi nằm bên trong block |
| Unchecked exception ở initializer | Không buộc catch-or-declare theo quy tắc checked, nhưng có thể làm `new` thất bại ở runtime |

**Nhớ:** với initializer của named class, việc một constructor riêng đã khai báo đúng không làm các constructor còn lại được miễn khai báo.

## 13. Anonymous class là ngoại lệ đáng nhớ của quy tắc named class

Anonymous class là một lớp không có tên được khai báo ngay trong biểu thức tạo đối tượng:

~~~java
interface Action {
    void run();
}

Action action = new Action() {
    @Override
    public void run() {
        System.out.println("Action");
    }
};
~~~

Lập trình viên **không thể khai báo constructor tường minh** cho một anonymous class. Vì vậy nếu áp dụng máy móc điều kiện “phải có một constructor được khai báo tường minh”, anonymous class sẽ không bao giờ được viết initializer có checked exception.

Java có **quy tắc đặc biệt**: checked exception có thể phát sinh từ instance initializer của anonymous class được compiler phản ánh trong **constructor sinh ngầm** của anonymous class và trong phân tích khả năng ném của **biểu thức tạo anonymous class**. Do đó nơi gọi `new Interface() { ... }` có thể cần bắt hoặc khai báo checked exception đó.

Ví dụ hoàn chỉnh ở phần kế tiếp làm rõ.

## 14. Ví dụ Java 17 hoàn chỉnh: anonymous class có initializer ném `IOException`

Tệp `AnonymousInitializerDemo.java`:

~~~java
import java.io.IOException;

public class AnonymousInitializerDemo {
    interface Action {
        void run();
    }

    static String prepare(boolean fail) throws IOException {
        System.out.println("Khởi tạo anonymous");
        if (fail) throw new IOException("anonymous lỗi");
        return "OK";
    }

    static Action create(boolean fail) throws IOException {
        return new Action() {
            final String label = prepare(fail);

            @Override
            public void run() {
                System.out.println("Chạy: " + label);
            }
        };
    }

    public static void main(String[] args) {
        try {
            Action action = create(false);
            action.run();
            create(true);
        } catch (IOException ex) {
            System.out.println("Bắt lỗi: " + ex.getMessage());
        }
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 AnonymousInitializerDemo.java
java AnonymousInitializerDemo
~~~

Stdout chính xác:

~~~text
Khởi tạo anonymous
Chạy: OK
Khởi tạo anonymous
Bắt lỗi: anonymous lỗi
~~~

Lưu ý:

1. `new Action() { ... }` tạo một **anonymous class** triển khai interface `Action`.
2. `final String label = prepare(fail)` là instance field initializer của anonymous class; `prepare` có thể ném `IOException`.
3. Class anonymous không có explicit constructor, nhưng trường hợp này **được phép** theo quy tắc JLS §11.2.3.
4. Biểu thức tạo anonymous class trong `create()` có thể ném `IOException`, vì thế phương thức `create(boolean)` khai báo `throws IOException`.
5. Caller `main()` xử lý `IOException` bằng `catch`.
6. Nếu việc tạo anonymous class thất bại, phương thức `run()` của đối tượng mới **không được gọi**, vì đối tượng chưa được tạo thành công.

**Đừng nhầm:** việc interface `Action.run()` không khai báo `throws IOException` không cấm **constructor sinh ngầm của anonymous class** phát sinh `IOException` khi tạo đối tượng. Nhưng nếu đặt `throw new IOException(...)` trực tiếp vào **thân phương thức `run()`**, bạn vẫn phải tuân thủ hợp đồng override của `Action.run()`, nơi không cho phép checked exception này thoát ra.

## 15. Khác biệt với static field initializer và static initializer block

Đây là một đối chiếu rất quan trọng. Với **named class hoặc interface**, một static field initializer hoặc static initializer **không được để checked exception có thể thoát ra**. Không thể sửa bằng cách thêm `throws IOException` cho các constructor instance, bởi static initialization là cơ chế **khởi tạo lớp**.

Ví dụ sai:

~~~java
import java.io.IOException;

// CỐ Ý SAI:
class StaticInitializerBad {
    static String value = fetch();

    static String fetch() throws IOException {
        throw new IOException();
    }
}
~~~

Chạy `javac StaticInitializerBad.java` bị lỗi checked exception chưa được bắt/khai báo; không tồn tại cú pháp `static { ... } throws IOException` cho block cấp class.

Phương án có xử lý:

~~~java
import java.io.IOException;

class SafeStatic {
    static final String value;

    static {
        try {
            value = read();
        } catch (IOException ex) {
            throw new IllegalStateException("Không khởi tạo được class", ex);
        }
    }

    static String read() throws IOException {
        return "OK";
    }
}
~~~

Đoạn này là **lớp Java hợp lệ**, nhưng cần hiểu: khi static initializer thực sự ném một unchecked exception không phải `Error`, lỗi khởi tạo lớp ở runtime có thể được bao trong `ExceptionInInitializerError`; các lần dùng class tiếp theo cũng có thể gặp lỗi liên quan trạng thái khởi tạo class. Đây là **hợp đồng runtime của class initialization**, không phải cơ chế checked `throws` của constructor instance.

| Cơ chế | Có thể để checked exception thoát qua `throws` của constructor không? |
| --- | --- |
| Instance initializer của **named class** | Có, nếu tất cả explicit constructor khai báo phù hợp và class có ít nhất một constructor tường minh |
| Instance initializer của **anonymous class** | Có cơ chế riêng qua constructor sinh ngầm và biểu thức `new` anonymous |
| Static initializer của named class/interface | Không; phải xử lý checked exception tại chỗ |
| Thân constructor | Có; khai báo chính constructor phù hợp |
| Phần thân method thường | Có, theo catch-or-declare của method |

Đừng hiểu ngoại lệ checked do **static initializer** tạo ra là một trường hợp “cứ thêm `throws IOException` vào constructor thì sửa được”.

## 16. Instance initializer được chạy bao nhiêu lần với `this()` và kế thừa?

Một lượt tạo đối tượng hoàn tất bình thường bao gồm chuỗi khởi tạo của các lớp trong phân cấp. Theo logic thông thường:

- Superclass có instance initializers của nó; chúng chạy khi superclass được khởi tạo cho đối tượng.
- Sau khi phần khởi tạo superclass liên quan hoàn tất, instance initializers của subclass chạy.
- Với các constructor cùng lớp liên kết bằng `this(...)`, chúng **không làm phần initializer của chính lớp ấy chạy nhiều lần** trên cùng đối tượng.
- Nếu một initializer bị lỗi, các initializer hoặc phần constructor body phía sau nó trong cùng đường thực thi có thể không chạy.
- Caller không nhận được kết quả `new` thành công khi quá trình khởi tạo kết thúc bất thường.

Ví dụ minh họa thứ tự:

~~~java
class Base {
    {
        System.out.println("Base initializer");
    }

    Base() {
        System.out.println("Base constructor");
    }
}

class Derived extends Base {
    {
        System.out.println("Derived initializer");
    }

    Derived() {
        System.out.println("Derived constructor");
    }

    Derived(String label) {
        this();
        System.out.println("Derived constructor " + label);
    }
}
~~~

Nếu đặt trong một chương trình và gọi `new Derived("A")`, thứ tự phần in liên quan là:

~~~text
Base initializer
Base constructor
Derived initializer
Derived constructor
Derived constructor A
~~~

Đoạn này là **minh họa hai lớp**, không gồm phương thức `main`; stdout được suy ra từ thứ tự constructor chaining, không phải đầu ra của một tệp độc lập. Hành vi phù hợp với chương trình chạy hoàn chỉnh `NamedInitializerDemo` ở mục 7.

Nếu constructor của `Base` ném checked exception, constructor `Derived` gọi nó phải xử lý/khai báo theo luật constructor invocation. Nếu instance initializer của `Derived` cũng có thể ném loại checked khác, **mọi constructor explicit của `Derived`** phải công bố loại đó.

## 17. Checked exception khi tạo tài nguyên trong initializer: trách nhiệm cleanup

Một bẫy thiết kế: instance initializer có thể mở tài nguyên như stream, socket hoặc JDBC connection. Nếu mở tài nguyên con thành công rồi thao tác khởi tạo sau đó thất bại, **đối tượng bao ngoài chưa được tạo thành công** và caller không có tham chiếu đáng tin để gọi `close()` trên nó.

Mã minh họa vấn đề:

~~~java
// Minh họa trong một lớp có khai báo Path, IOException và API checkHeader.
class FragileReader implements AutoCloseable {
    java.io.InputStream in;

    {
        in = java.nio.file.Files.newInputStream(path);
        checkHeader(in); // Nếu ném IOException, tạo FragileReader thất bại.
    }

    FragileReader() throws java.io.IOException { }

    @Override
    public void close() throws java.io.IOException {
        if (in != null) in.close();
    }
}
~~~

Đoạn này **không độc lập** (cần định nghĩa `path` và `checkHeader`). Nó minh họa một nguy cơ: `try (FragileReader r = new FragileReader())` của caller **chỉ tự đóng `r` nếu resource expression khởi tạo thành công**. Nếu lỗi xảy ra **trong initializer của `FragileReader`**, `r` chưa được gán một đối tượng hoàn chỉnh; `try-with-resources` ở caller không tự `close()` tài nguyên nội bộ `in` đã mở dở.

Hướng an toàn hơn:

1. Đặt quá trình cấp phát và kiểm tra vào **factory method** hoặc constructor có kiểm soát.
2. Nếu một bước sau khi mở tài nguyên thất bại, **đóng tài nguyên đã cấp phát trong chính nơi cấp phát**.
3. Dùng `try-with-resources` cho tài nguyên con nếu có thể thiết kế đường trả quyền sở hữu an toàn.
4. Giữ lỗi chính và lỗi đóng phụ bằng cause/suppressed khi phù hợp.
5. Tránh “xuất bản” tham chiếu `this` của đối tượng chưa khởi tạo xong tới code bên ngoài.

Quy tắc checked exception giúp caller biết có thể thất bại, nhưng **không tự rollback trạng thái hoặc đóng các tài nguyên đã cấp phát dở**.

## 18. Một factory method có thể giúp hợp đồng rõ hơn

Thay vì đặt một thao tác mở dễ thất bại trong field initializer:

~~~java
class FragileClient {
    final String configuration = readConfiguration();

    FragileClient() throws java.io.IOException { }

    static String readConfiguration() throws java.io.IOException {
        return "mode=prod";
    }
}
~~~

bạn có thể thực hiện bước I/O trước, sau đó tạo đối tượng chỉ với dữ liệu đã chuẩn bị:

~~~java
import java.io.IOException;

final class Client {
    private final String configuration;

    private Client(String configuration) {
        this.configuration = configuration;
    }

    static Client open() throws IOException {
        String configuration = readConfiguration();
        return new Client(configuration);
    }

    static String readConfiguration() throws IOException {
        return "mode=prod";
    }

    String configuration() {
        return configuration;
    }
}
~~~

Đây là lớp Java độc lập hợp lệ, tuy không có `main`. Caller dùng `Client.open()`, bắt hoặc khai báo `IOException`; constructor private không có checked exception. Ưu điểm:

- Đường mở/chuẩn bị dữ liệu dễ nhìn ở method có tên và `throws` rõ ràng.
- Mỗi constructor không phải khai báo lỗi từ một initializer phức tạp.
- Có thể xử lý tài nguyên tạm trong factory trước khi chuyển sang trạng thái đối tượng hoàn chỉnh.
- Dễ viết kiểm thử từng đường thành công/thất bại và xác định điểm chuyển ownership.

Không bắt buộc mọi lớp có I/O phải dùng factory. Nếu constructor có ý nghĩa công khai “tạo object có thể lỗi I/O”, khai báo `throws IOException` trên các constructor cũng là thiết kế hợp lệ. Chọn cách nào tùy ranh giới API và khả năng quản lý trạng thái thất bại.

## 19. Các tệp cố ý sai để nhận diện lỗi compiler

Các đoạn sau là **ví dụ kiểm thử biên dịch âm**, không phải chương trình chạy.

### 19.1. Thiếu constructor explicit

~~~java
import java.io.IOException;

class NoConstructorBad {
    String value = fetch();
    static String fetch() throws IOException {
        throw new IOException();
    }
}
~~~

`javac` báo dạng:

~~~text
error: unreported exception IOException; must be caught or declared to be thrown
~~~

Nguyên nhân là initializer của named class có thể ném checked `IOException`, nhưng lớp không có explicit constructor nào khai báo nó.

### 19.2. Một trong nhiều constructor không khai báo

~~~java
import java.io.IOException;

class OneMissingThrowsBad {
    String value = fetch();
    OneMissingThrowsBad() throws IOException { }
    OneMissingThrowsBad(int mode) { }
    static String fetch() throws IOException {
        throw new IOException();
    }
}
~~~

`javac` cũng từ chối. Việc constructor đầu khai báo đúng **không bù cho constructor thứ hai**.

### 19.3. Static initializer có checked exception chưa xử lý

~~~java
import java.io.IOException;

class StaticInitializerBad {
    static String value = fetch();
    static String fetch() throws IOException {
        throw new IOException();
    }
}
~~~

`javac` từ chối; đây là quy tắc **static initialization**, không thể sửa chỉ bằng khai báo `throws` trên instance constructors.

### 19.4. Constructor body ném checked exception chưa khai báo

~~~java
import java.io.IOException;

class ConstructorBodyBad {
    ConstructorBodyBad() {
        throw new IOException("body");
    }
}
~~~

`javac` từ chối vì thân constructor trực tiếp ném checked `IOException` nhưng constructor chưa xử lý/khai báo. Đây là quy tắc constructor body thông thường, không phải điều kiện “mọi constructor” của instance initializer.

Cả bốn trường hợp được kiểm chứng với `javac --release 17`; thông báo có thể chỉ vào biểu thức khác nhau, nhưng nguyên nhân đều liên quan khả năng ném checked exception không phù hợp với ngữ cảnh.

## 20. Phân biệt lỗi trong initializer của object và lỗi class initialization

Các tên “initializer” rất dễ gây hiểu nhầm:

| Thuộc tính | Instance initializer | Static initializer |
| --- | --- | --- |
| Gắn với | Từng đối tượng | Lớp/interface theo quy tắc class initialization |
| Ví dụ | `String x = load();`, `{ check(); }` | `static String x = load();`, `static { check(); }` |
| Tạo mới object liên tiếp có chạy lại? | Có, cho mỗi lần khởi tạo đối tượng tương ứng | Không tự chạy lại cho mỗi `new` |
| Checked exception thoát ra trong named class | Có thể, nếu tất cả constructor explicit khai báo bao phủ | Không cho phép thoát trực tiếp |
| Điểm xử lý thường gặp | Caller của `new` hoặc constructor/factory | Khối `try/catch` trong static initialization, hoặc unchecked failure ở runtime |
| Có thể làm object không tạo xong? | Có | Có thể khiến class không khởi tạo thành công, ngăn sử dụng |

Nếu static initializer làm class initialization thất bại, người gọi có thể thấy `ExceptionInInitializerError` hoặc lỗi liên quan trạng thái class, tùy tình huống. **Không phải cứ thấy `ExceptionInInitializerError` là lỗi ở instance initializer**; tên exception này đặc biệt liên quan tới class initialization.

## 21. Lỗi thường gặp và cách sửa

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Instance field initializer gọi API checked nhưng lớp không có constructor | Lỗi compiler | Viết constructor explicit với `throws`, hoặc xử lý checked exception trong initializer |
| Chỉ constructor không tham số có `throws`, constructor overload thì không | Lỗi compiler cho named class | Mọi explicit constructor phải công bố các checked exception từ initializer |
| Nghĩ `this(...)` đã gọi constructor khác nên constructor hiện tại không cần `throws` | Bỏ qua nghĩa vụ checked exception từ initializer và lời gọi constructor đích | Khai báo/thiết kế đủ ở mọi constructor |
| Đặt `throws IOException` sau dấu `{ ... }` của instance initializer | Cú pháp Java không hợp lệ | `throws` nằm trong khai báo constructor/method |
| Đặt checked `throw` vô điều kiện trong instance initializer | Có thể vi phạm quy tắc block phải hoàn tất bình thường | Dùng đường có điều kiện và tuân thủ checked exception |
| Nghĩ constructor body luôn chạy trước field initializer | Dự đoán sai stdout hoặc trạng thái | Theo dõi thứ tự superclass → initializer cùng lớp → body constructor |
| Nghĩ instance initializer lỗi vẫn tiếp tục chạy các initializer phía sau | Đọc sai luồng điều khiển | Xem điểm ném là đường thoát bất thường |
| Bắt checked exception trong initializer rồi bỏ trống | Tạo object trạng thái sai, che lỗi thật | Phục hồi hợp lệ hoặc truyền lỗi có ngữ nghĩa |
| Bọc `IOException` thành unchecked mà bỏ cause | Mất dấu vết kỹ thuật | Dùng constructor `(message, cause)` |
| Dùng instance `throws` để sửa lỗi ở static initializer | Không có tác dụng | Bắt checked lỗi trong static initializer hoặc thiết kế lại |
| Cho rằng anonymous class phải khai báo constructor explicit | Anonymous class không được khai báo constructor | Áp dụng cơ chế constructor sinh ngầm và catch-or-declare tại biểu thức `new` |
| Khởi tạo tài nguyên dở rồi ném, mong caller tự gọi `close()` | Có thể rò rỉ tài nguyên | Quản lý cleanup trong nơi cấp phát trước khi chuyển ownership |
| Nhầm checked với unchecked | Khai báo `throws` thiếu hoặc thêm vô ích | Xem quan hệ kiểu với `RuntimeException`/`Error` |
| Đưa logic I/O lớn vào nhiều field initializers | Khó kiểm soát lỗi, side effect và test | Cân nhắc factory hoặc constructor khởi tạo rõ từng bước |

## 22. Checklist khi thiết kế class có initializer có thể lỗi

1. **Xác định chính xác chỗ nào có thể ném checked exception:** field initializer, instance block, constructor body, lời gọi `super`, `this` hay static initializer?
2. **Đây là named class hay anonymous class?** Hai trường hợp có quy tắc công bố lỗi khác nhau.
3. Với named class, **có ít nhất một constructor explicit chưa?**
4. **Mọi constructor explicit có `throws` bao phủ từng checked exception thoát từ initializer chưa?**
5. Nếu initializer gọi API I/O, **caller của `new` có đường `catch` hoặc `throws` đúng chưa?**
6. Các initializer có chạy **đúng thứ tự mã nguồn** không? Có phụ thuộc vào field chưa được gán giá trị không?
7. Nếu một initializer thất bại, **trạng thái/tài nguyên đã cấp phát trước đó** được giải phóng thế nào?
8. Nếu code khởi tạo có thể được khôi phục, giá trị dự phòng có thật sự **đảm bảo bất biến của object** không?
9. **Có nên chuyển thao tác phức tạp sang factory** để biểu diễn lỗi và quyền sở hữu tài nguyên rõ hơn?
10. Với anonymous class, checked exception từ initializer có được **bắt/khai báo tại biểu thức tạo đối tượng** chưa?
11. **Không lẫn với static initializer** hoặc `ExceptionInInitializerError`.
12. **Kiểm thử cả đường thành công, lỗi field và lỗi block** bằng ví dụ và xác minh constructor body có được chạy hay không.

## 23. Tự kiểm tra kiến thức

**Câu 1.** Named class có `String value = load();` với `load() throws IOException`, nhưng không khai báo constructor nào. Có biên dịch không?

**Đáp án:** Không. Named class phải có ít nhất một constructor khai báo tường minh, và mọi constructor explicit phải có `throws` phù hợp cho checked exception từ initializer.

**Câu 2.** Named class có hai constructor; chỉ một constructor `throws IOException`. Instance initializer có thể ném `IOException`. Hợp lệ không?

**Đáp án:** Không. **Mọi** constructor explicit đều phải khai báo `IOException` hoặc superclass phù hợp.

**Câu 3.** Có thể gắn `throws IOException` trực tiếp vào dấu ngoặc của instance initializer block không?

**Đáp án:** Không. Block không có chữ ký; phải công bố từ constructor hoặc xử lý lỗi trong block.

**Câu 4.** Nếu initializer bắt `IOException` và trả fallback hợp lệ, constructor có bắt buộc `throws IOException` không?

**Đáp án:** Không, nếu không còn đường nào từ initializer có thể để `IOException` thoát ra và không có nghĩa vụ checked exception khác.

**Câu 5.** Tại sao code `new Example()` có thể phải `catch IOException` dù thân `Example()` rỗng?

**Đáp án:** Vì instance field initializer hoặc instance block chạy trong quá trình tạo đối tượng có thể ném checked exception và được công bố qua constructor.

**Câu 6.** Constructor A gọi `this()` đến constructor B; instance initializers của cùng lớp có chạy hai lần không?

**Đáp án:** Không; chúng chạy một lượt cho một quá trình khởi tạo instance của lớp đó.

**Câu 7.** Instance field initializer ném ngoại lệ trước một instance block. Block phía sau có chạy không?

**Đáp án:** Không; quá trình khởi tạo cùng lớp đã kết thúc bất thường ở điểm ném.

**Câu 8.** Anonymous class có được viết field initializer gọi phương thức `throws IOException` không?

**Đáp án:** Có thể; Java suy ra checked exception trong constructor sinh ngầm và yêu cầu xử lý/khai báo khi biểu thức tạo anonymous class có thể ném.

**Câu 9.** Thêm `throws IOException` vào constructor có sửa được một **static field initializer** ném checked `IOException` không?

**Đáp án:** Không. Static initializer phải tự xử lý checked exception hoặc thay đổi thiết kế.

**Câu 10.** Nếu object khởi tạo dở sau khi đã mở stream, caller dùng `try-with-resources` trên object ấy có chắc đóng được stream không?

**Đáp án:** Không. Caller chưa có object hoàn chỉnh; constructor/factory phải tự quản lý tài nguyên đã cấp phát khi thất bại.

**Câu 11.** Bọc checked exception thành unchecked có tự động bảo toàn lỗi ban đầu không?

**Đáp án:** Không. Cần truyền `cause` rõ ràng, ví dụ `new IllegalStateException("không khởi tạo được", original)`.

**Câu 12.** Checked exception trong thân constructor có phải khiến **mọi constructor overload** công bố loại đó không?

**Đáp án:** Không chỉ vì lỗi nằm trong **thân một constructor**. Quy tắc “mọi constructor” là yêu cầu đặc biệt đối với checked exception thoát từ **instance initializer của named class**. Các constructor khác vẫn có nghĩa vụ riêng nếu gọi constructor đó qua `this(...)` hoặc thực hiện thao tác checked.

## 24. Tài liệu tham khảo

- [Java Language Specification 17 — §11.2.3, Exception Checking](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.2.3): quy tắc **mọi explicit constructor** của named class và ngoại lệ riêng cho anonymous class.
- [Java Language Specification 17 — §8.3.2, Field Initialization](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.3.2): các biểu thức khởi tạo field.
- [Java Language Specification 17 — §8.6, Instance Initializers](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.6): quy tắc instance initializer blocks và khả năng hoàn tất bình thường.
- [Java Language Specification 17 — §8.8, Constructor Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.8): constructors, explicit constructor invocation và mệnh đề `throws`.
- [Java Language Specification 17 — §12.5, Creation of New Class Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.5): thứ tự và điều kiện khởi tạo instance.
- [Java Language Specification 17 — §15.9.5, Anonymous Class Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9.5): ngữ nghĩa anonymous class và constructor sinh ngầm.
- [Java Language Specification 17 — §8.7, Static Initializers](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.7): phân biệt static initialization với instance initialization.

**Kết luận:** checked exception có thể xuất hiện **trước thân constructor** ở instance field initializer hoặc instance initializer block. Với **named class**, Java yêu cầu **ít nhất một explicit constructor** và **mọi constructor explicit** đều công bố các checked exception ấy trong `throws`, hoặc xử lý để chúng không thoát khỏi initializer. Với **anonymous class**, compiler dùng constructor sinh ngầm và chuyển nghĩa vụ catch-or-declare tới biểu thức tạo đối tượng. Hiểu đúng ranh giới này giúp thiết kế constructor, factory, tài nguyên và hợp đồng lỗi an toàn.
