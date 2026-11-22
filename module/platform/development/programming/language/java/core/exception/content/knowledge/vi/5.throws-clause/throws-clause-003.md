# Quan hệ giữa kiểu ngoại lệ khai báo trong `throws` và lớp con thực sự được ném trong Java

Một phương thức Java có thể khai báo `throws IOException` nhưng khi chạy lại ném một đối tượng `FileNotFoundException` hoặc `EOFException`. Điều đó hoàn toàn hợp lệ vì các loại này là **lớp con của `IOException`**. Mệnh đề `throws` mô tả **hợp đồng ngoại lệ checked mà người gọi phải tính đến khi biên dịch**, còn đối tượng được ném tại runtime vẫn có **kiểu thực tế** của chính nó.

Ví dụ ngắn:

```java
static void load() throws java.io.IOException {
    throw new java.io.FileNotFoundException("config.txt");
}
```

Đây là một phương thức minh họa, cần đặt trong lớp Java. `FileNotFoundException extends IOException`, nên `throws IOException` đủ để trình biên dịch chấp nhận ngoại lệ checked này được lan ra ngoài. Ở người gọi:

```java
try {
    load();
} catch (java.io.IOException ex) {
    System.out.println(ex.getClass().getSimpleName());
}
```

Kết quả in là `FileNotFoundException`, **không phải `IOException`**. Handler `catch (IOException)` bắt được đối tượng kiểu con, nhưng việc bắt không biến đối tượng thành một `IOException` thuần túy.

Để hiểu đúng cần tách ba lớp thông tin:

1. **Kiểu ngoại lệ được khai báo (`declared exception type`):** kiểu xuất hiện sau `throws` ở chữ ký phương thức.
2. **Kiểu ngoại lệ được ném thực tế (`actual runtime exception type`):** lớp của đối tượng `Throwable` đi ra từ câu lệnh `throw` hoặc API được gọi.
3. **Kiểu ngoại lệ mà caller bắt (`catch parameter type`):** kiểu trong nhánh `catch` của người gọi; handler phù hợp nếu đối tượng thực tế thuộc kiểu đó hoặc một lớp con của nó.

## 1. `throws` là hợp đồng tại thời điểm biên dịch

Một khai báo phương thức có dạng:

```java
static String read(String path) throws java.io.IOException {
    return java.nio.file.Files.readString(
            java.nio.file.Path.of(path));
}
```

Đây là phương thức minh họa, phụ thuộc tệp thật khi chạy. Phần `throws IOException` cho biết phương thức được phép để `IOException` hoặc những lớp con checked của nó truyền ra. Với một lời gọi có thể ném `IOException`, trình biên dịch yêu cầu mã gọi phải **bắt (`catch`) hoặc tiếp tục khai báo (`throws`)** ngoại lệ checked đó.

Ví dụ caller hợp lệ:

```java
static String readAtService(String path)
        throws java.io.IOException {
    return read(path);
}
```

Hoặc caller có handler:

```java
static void printFile(String path) {
    try {
        System.out.println(read(path));
    } catch (java.io.IOException ex) {
        System.out.println("Không đọc được tệp");
    }
}
```

Các đoạn này là phương thức minh họa và phải đặt trong cùng phạm vi có thể gọi `read`.

**Điểm cần nhớ:** khai báo `throws IOException` không tự ném gì cả. Một lời gọi có thể trả về bình thường. Mệnh đề này cũng không hứa rằng ngoại lệ tại runtime phải có **đúng lớp** `IOException`; lớp con như `NoSuchFileException` hay `FileNotFoundException` đều có thể xuất hiện nếu thao tác tương ứng thực sự ném chúng.

Đồng thời, `throws` **không phải danh sách đầy đủ của mọi ngoại lệ có thể xảy ra lúc chạy**: ngoại lệ unchecked như `IllegalArgumentException`, `NullPointerException` và các `Error` có thể thoát ra mà không cần xuất hiện trong mệnh đề `throws`.

## 2. Tại sao khai báo kiểu cha lại bao phủ lớp con?

Trong Java, quan hệ kế thừa cho phép một đối tượng thuộc lớp con được sử dụng ở vị trí yêu cầu lớp cha. Quy tắc này cũng áp dụng với ngoại lệ.

Một phần cây điển hình:

```text
Throwable
├── Error
└── Exception
    ├── IOException
    │   ├── FileNotFoundException
    │   └── EOFException
    └── RuntimeException
        ├── IllegalArgumentException
        │   └── NumberFormatException
        └── IllegalStateException
```

Cây chỉ liệt kê một số lớp; nhiều lớp ngoại lệ khác không được biểu diễn.

Với cây này:

- `throws IOException` có thể bao phủ `FileNotFoundException` và `EOFException`.
- `throws Exception` có thể bao phủ `IOException` và nhiều ngoại lệ checked khác thuộc `Exception`; nó thường **quá rộng** nếu API chỉ có thể phát sinh lỗi I/O có ý nghĩa.
- `throws FileNotFoundException` **không** bao phủ một `IOException` thông thường, vì `IOException` là **kiểu cha**, không phải con của `FileNotFoundException`.
- `throws RuntimeException` là cú pháp hợp lệ, nhưng không cần thiết để thỏa quy tắc checked exception vì `RuntimeException` và các lớp con là unchecked.
- `throws Exception` **không mô tả `Error`**: `Error` là nhánh khác của `Throwable`. Dù vậy `Error` vẫn có thể xảy ra mà không phải khai báo.

### Chiều quan hệ quan trọng

Giả sử `ChildException extends ParentException`:

```java
class ParentException extends Exception {}
class ChildException extends ParentException {}

static void childOperation() throws ParentException {
    throw new ChildException();
}
```

Đoạn mã là các khai báo minh họa cần đặt trong một lớp hoặc tổ chức tệp Java hợp lệ. Nó biên dịch được: phương thức khai báo kiểu cha checked và ném kiểu con.

Chiều ngược lại:

```java
static void invalidOperation() throws ChildException {
    throw new ParentException();
}
```

Đoạn trên **cố ý không biên dịch**: `ParentException` không phải là một `ChildException`, và ngoại lệ checked kiểu cha được ném không được bao phủ bởi khai báo chỉ cho phép kiểu con. Sửa bằng cách đổi khai báo thành `throws ParentException`, hoặc chỉ ném kiểu con, hoặc bắt lỗi trong phương thức.

Nói cách khác, với ngoại lệ checked **được phép thoát khỏi thân phương thức**, kiểu thực tế phát sinh theo các đường chạy phải có khả năng được khai báo/bắt theo một kiểu phù hợp. Việc caller thấy kiểu cha trong hợp đồng **không ép** runtime tạo một đối tượng cha.

## 3. Phân biệt ba thời điểm: khai báo, ném và bắt

| Giai đoạn | Mã liên quan | Điều gì được xác định? |
| --- | --- | --- |
| Khai báo API | `void load() throws IOException` | Loại checked exception mà caller phải chuẩn bị theo kiểu tĩnh của lời gọi |
| Thao tác thực tế | `throw new FileNotFoundException("...")` | Đối tượng lỗi mang kiểu runtime `FileNotFoundException` |
| Xử lý của caller | `catch (IOException ex)` | Handler được chọn vì `FileNotFoundException` là subtype của `IOException` |

Ở thời điểm chạy, Java không thay đối tượng `FileNotFoundException` thành `IOException` chỉ vì chữ ký khai báo kiểu cha. Do đó:

```java
if (ex instanceof java.io.FileNotFoundException) {
    // Đây là một lỗi FileNotFoundException thực sự.
}
```

Có thể dùng `instanceof` khi cần phân loại lỗi trong handler tổng quát. Nếu các kiểu lỗi đòi hỏi hành động khác nhau, các nhánh `catch` cụ thể thường dễ đọc hơn:

```java
try {
    readDocument();
} catch (java.io.FileNotFoundException ex) {
    // Xử lý riêng khi thao tác thực sự ném FileNotFoundException.
} catch (java.io.IOException ex) {
    // Xử lý các IOException còn lại.
}
```

Đây là cấu trúc minh họa: `readDocument()` cần là phương thức có khai báo/lời gọi phù hợp. `FileNotFoundException` phải đứng **trước** `IOException` vì nhánh cha đứng trước sẽ bắt luôn lỗi con, khiến nhánh con phía sau không thể đến được.

## 4. Ví dụ Java 17+ hoàn chỉnh: `throws IOException`, runtime ném nhiều loại

Lưu tệp **`DeclaredVsActualExceptionDemo.java`**:

```java
import java.io.EOFException;
import java.io.FileNotFoundException;
import java.io.IOException;

public class DeclaredVsActualExceptionDemo {

    // Một hợp đồng checked tổng quát cho các thất bại I/O.
    static void load(String scenario) throws IOException {
        switch (scenario) {
            case "missing" ->
                    throw new FileNotFoundException("settings.properties");
            case "short" ->
                    throw new EOFException("incomplete content");
            case "other" ->
                    throw new IOException("read failed");
            case "state" ->
                    throw new IllegalStateException("resource is closed");
            default ->
                    System.out.println("load: success");
        }
    }

    static void caller(String scenario) {
        System.out.println("CASE " + scenario);
        try {
            load(scenario);
            System.out.println("caller: completed");
        } catch (IOException ex) {
            System.out.println("caught as: IOException");
            System.out.println(
                    "actual type: " + ex.getClass().getSimpleName());
            System.out.println("message: " + ex.getMessage());
        } catch (IllegalStateException ex) {
            System.out.println(
                    "unchecked type: " + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        caller("ok");
        caller("missing");
        caller("short");
        caller("other");
        caller("state");
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 DeclaredVsActualExceptionDemo.java
java DeclaredVsActualExceptionDemo
```

**Stdout xác định:**

```text
CASE ok
load: success
caller: completed
CASE missing
caught as: IOException
actual type: FileNotFoundException
message: settings.properties
CASE short
caught as: IOException
actual type: EOFException
message: incomplete content
CASE other
caught as: IOException
actual type: IOException
message: read failed
CASE state
unchecked type: IllegalStateException
```

### Phân tích kết quả

**`missing`:** phương thức khai báo `throws IOException`, nhưng đối tượng do `throw new FileNotFoundException(...)` tạo có lớp thực tế `FileNotFoundException`. Handler khai báo `IOException` bắt được vì quan hệ kế thừa. Phương thức `getClass().getSimpleName()` vẫn trả về `FileNotFoundException`.

**`short`:** cùng chữ ký `throws IOException` nhưng đối tượng thực tế là `EOFException`, một lớp con khác của `IOException`. Caller không cần biết trước **chính xác** một trong hai lớp con sẽ xuất hiện để biên dịch và xử lý mọi lỗi I/O bằng handler `IOException`.

**`other`:** trường hợp này đối tượng thực sự là `IOException`; kiểu khai báo và runtime tình cờ trùng nhau.

**`state`:** `IllegalStateException` không nằm dưới `IOException`; nó là `RuntimeException` unchecked. Java vẫn cho phép ném nó dù `load` chỉ khai báo `throws IOException`. Handler `catch (IOException)` không bắt nó; nhánh `catch (IllegalStateException)` được chọn.

**`ok`:** `load` không ném lỗi và caller in `"completed"`. Khai báo `throws` chỉ mô tả khả năng, không đảm bảo sẽ có ngoại lệ.

Ví dụ mô phỏng bằng các câu `throw` trực tiếp nên không phụ thuộc đường dẫn thực hay lỗi đặc thù của hệ điều hành.

## 5. Caller phải xử lý theo kiểu khai báo, có thể phân nhánh theo kiểu runtime

Khi viết một lời gọi, trình biên dịch xem **kiểu tĩnh của phương thức được gọi** và các ngoại lệ checked được khai báo/được phân tích theo quy tắc ngôn ngữ. Với:

```java
static void load() throws java.io.IOException {
    // Có thể thực hiện đọc dữ liệu và phát sinh lỗi I/O.
}
```

Một caller thực tế phải xử lý hoặc khai báo `IOException`, chẳng hạn:

```java
static void operation() throws java.io.IOException {
    load();
}
```

Nếu bỏ `throws IOException` trong `operation()` mà không thêm `catch`, trình biên dịch báo lỗi ngoại lệ checked chưa được bắt/khai báo. Nó không cần và thường không thể chứng minh trước chính xác lớp con nào sẽ được ném trên mọi lần chạy của `load`.

### Có nên bắt riêng lớp con?

Nếu caller biết cách xử lý khác nhau, có thể đặt handler theo thứ tự con → cha:

```java
try {
    load();
} catch (java.io.FileNotFoundException ex) {
    // Có thể báo thiếu tài nguyên hoặc chọn đường dẫn thay thế.
} catch (java.io.IOException ex) {
    // Xử lý các lỗi I/O khác theo hợp đồng chung.
}
```

Ở đây `load()` được giả định có thể phát sinh `IOException`. Mặc dù chữ ký khai báo `IOException`, một nhánh `FileNotFoundException` riêng vẫn có ý nghĩa vì lớp con đó có thể được ném tại runtime. Thứ tự `catch` được kiểm tra theo quan hệ kế thừa; không đặt `catch (IOException)` trước nhánh `FileNotFoundException`.

Nếu tất cả lỗi I/O đều được xử lý cùng một cách, chỉ một `catch (IOException)` sẽ ngắn gọn hơn. Không cần tạo danh sách handler cho mọi lớp con chỉ vì chúng tồn tại trong JDK.

### Nếu chỉ bắt lớp con thì đã xử lý đủ chưa?

Không, nếu phương thức có thể ném cả các loại `IOException` khác. Ví dụ:

```java
static void tooNarrow() {
    try {
        load();
    } catch (java.io.FileNotFoundException ex) {
        System.out.println("File not found");
    }
}
```

Đây là **ví dụ cố ý không biên dịch** nếu `load()` có khai báo `throws IOException` như trên: một `IOException` khác ngoài `FileNotFoundException` vẫn có thể lan ra, nhưng `tooNarrow()` không bắt hoặc khai báo nó. Để sửa, thêm `catch (IOException)` sau nhánh con hoặc khai báo `throws IOException` trên `tooNarrow`.

## 6. Kiểu khai báo càng rộng, hợp đồng caller càng rộng

Giả sử cùng một phương thức chỉ thật sự cần báo lỗi thiếu tệp:

```java
static void precise() throws java.io.FileNotFoundException {
    throw new java.io.FileNotFoundException("missing.txt");
}
```

Ở đây `throws FileNotFoundException` cho caller hợp đồng checked hẹp. Caller có thể bắt `FileNotFoundException` hoặc khai báo một kiểu cha phù hợp như `IOException`.

Trong khi đó:

```java
static void broad() throws Exception {
    throw new java.io.FileNotFoundException("missing.txt");
}
```

`throws Exception` cũng hợp lệ nhưng làm caller phải xem xét phạm vi checked exception rộng hơn. Nếu caller chỉ có `catch (IOException)`, khai báo `throws Exception` còn có thể khiến mã gọi không biên dịch vì các kiểu checked `Exception` khác vẫn được xem là có thể thoát ra.

| Kiểu khai báo | Loại checked exception được cho phép thoát ra | Tác động tới người gọi |
| --- | --- | --- |
| `throws FileNotFoundException` | `FileNotFoundException` và lớp con của nó | Hợp đồng hẹp, rõ lỗi chuyên biệt |
| `throws IOException` | `IOException` và các lớp con | Caller xử lý nhóm lỗi I/O |
| `throws Exception` | Các checked exception thuộc `Exception` | Rộng, caller khó biết chính xác nhóm sự cố |
| Không khai báo checked exception | Không được cho checked exception thoát ra không được bắt theo cách thông thường | Caller không bị buộc xử lý checked exception của phương thức này |
| `throws IOException, SQLException` | Hai nhánh checked exception độc lập | Caller xem xét cả lỗi I/O và SQL |

Mục tiêu không phải lúc nào cũng khai báo **lớp lá hẹp nhất**. Một API đọc cấu hình có thể ném nhiều lớp con `IOException`; khai báo `throws IOException` thường là mức trừu tượng đúng. Ngược lại, `throws Exception` làm mất nhiều giá trị của hợp đồng nếu phương thức chỉ có lỗi I/O.

Hãy chọn kiểu khai báo theo **nhóm lỗi mà caller có thể xử lý hợp lý**, khả năng thay đổi triển khai và sự ổn định của API.

## 7. Ghi đè (`override`): phương thức con được khai báo checked exception hẹp hơn

Quan hệ cha/con còn ràng buộc **chữ ký của phương thức ghi đè**. Giả sử một interface mô tả nguồn tài liệu, có thể xảy ra lỗi I/O:

```java
interface DocumentSource {
    String fetch(String name) throws java.io.IOException;
}
```

Lớp triển khai có thể chỉ ném ngoại lệ hẹp hơn:

```java
class LocalDocumentSource implements DocumentSource {
    @Override
    public String fetch(String name)
            throws java.io.FileNotFoundException {
        if (name.isBlank()) {
            throw new java.io.FileNotFoundException("name is blank");
        }
        return "document";
    }
}
```

Đây là các khai báo minh họa, phải đặt trong package/tệp Java hợp lệ. `FileNotFoundException` là subtype của `IOException`, nên cách override này được phép.

Quy tắc checked exception khi override:

- Phương thức ghi đè có thể **không khai báo checked exception**, nếu triển khai xử lý mọi checked exception bên trong.
- Có thể khai báo **kiểu checked hẹp hơn** thuộc phạm vi ngoại lệ mà phương thức cha/interface cho phép.
- Không được mở rộng bằng một checked exception mới hoặc rộng hơn mà phương thức cha không cho phép, chẳng hạn từ `throws IOException` sang `throws Exception`.
- Có thể ném **unchecked exception** bất kể việc phương thức cha có khai báo hay không; ràng buộc trên áp dụng cho checked exception.
- Nếu một lớp thực hiện nhiều interface có cùng phương thức nhưng hợp đồng checked exception khác nhau, triển khai phải thỏa đồng thời các hợp đồng liên quan; không tự lấy hợp của tất cả loại checked exception để khai báo tùy ý.

### Ví dụ Java 17+ hoàn chỉnh: interface và lớp triển khai

Lưu tệp **`OverrideThrowsDemo.java`**:

```java
import java.io.FileNotFoundException;
import java.io.IOException;

public class OverrideThrowsDemo {

    interface DocumentSource {
        String fetch(String name) throws IOException;
    }

    static final class LocalDocumentSource implements DocumentSource {
        @Override
        public String fetch(String name)
                throws FileNotFoundException {
            if ("missing".equals(name)) {
                throw new FileNotFoundException(name + ".txt");
            }
            return "loaded:" + name;
        }
    }

    static void useInterface(DocumentSource source) {
        try {
            System.out.println(source.fetch("missing"));
        } catch (IOException ex) {
            System.out.println(
                    "interface caller catches: "
                    + ex.getClass().getSimpleName());
        }
    }

    static void useConcrete(LocalDocumentSource source) {
        try {
            System.out.println(source.fetch("missing"));
        } catch (FileNotFoundException ex) {
            System.out.println(
                    "concrete caller catches: "
                    + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) throws FileNotFoundException {
        LocalDocumentSource source = new LocalDocumentSource();
        useInterface(source);
        useConcrete(source);
        System.out.println(source.fetch("found"));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 OverrideThrowsDemo.java
java OverrideThrowsDemo
```

**Stdout:**

```text
interface caller catches: FileNotFoundException
concrete caller catches: FileNotFoundException
loaded:found
```

**Vì sao hai caller khác hợp đồng nhưng cùng thấy một loại ngoại lệ?**

- `useInterface` nhận biến `DocumentSource`. Theo **kiểu tĩnh của lời gọi**, chữ ký `fetch` của interface có `throws IOException`; vì thế handler `IOException` phù hợp cho kiểm tra biên dịch.
- `useConcrete` nhận biến `LocalDocumentSource`. Trình biên dịch nhìn thấy khai báo override hẹp hơn `throws FileNotFoundException`, nên bắt riêng lớp con là đủ đối với checked exception này.
- Cả hai cùng gọi triển khai `LocalDocumentSource.fetch` ở runtime, và đối tượng lỗi được ném đều là `FileNotFoundException`. Khác nhau ở **thông tin kiểu có sẵn tại thời điểm biên dịch**, không phải runtime ép lỗi thành lớp cha.
- `source.fetch("found")` trả `"loaded:found"` và không ném checked exception trong nhánh này; nhưng chữ ký concrete vẫn báo có khả năng `throws FileNotFoundException`. Trong `main`, lần gọi cuối cũng được trình biên dịch kiểm tra theo chữ ký concrete `throws FileNotFoundException`, vì vậy chính `main` khai báo `throws FileNotFoundException` để chương trình đầy đủ biên dịch được.

### Thứ tự quan hệ override: ví dụ không hợp lệ

```java
interface Reader {
    void read() throws java.io.IOException;
}

class InvalidReader implements Reader {
    @Override
    public void read() throws Exception {
        // ...
    }
}
```

Ví dụ trên **cố ý không biên dịch** vì `throws Exception` rộng hơn `throws IOException` trong hợp đồng cha. Caller nhận `Reader` chỉ được yêu cầu tính đến `IOException`; nếu triển khai được phép thêm mọi checked `Exception` khác, hợp đồng kiểu cha sẽ bị phá vỡ.

Một lớp ghi đè có thể dùng `throws FileNotFoundException` hoặc không có checked `throws`, nhưng không thể tùy ý tăng mức rủi ro checked exception mà kiểu cha đã công bố.

## 8. Chú ý: `throws` không xác định kiểu thực tế của đối tượng trong `catch`

Trong Java, đoạn:

```java
catch (java.io.IOException ex) {
    // ...
}
```

định nghĩa **kiểu tham chiếu** của biến `ex` tại thời điểm biên dịch. Nó không thay đổi lớp của đối tượng. Nếu đối tượng là `FileNotFoundException` thì:

```java
ex instanceof java.io.FileNotFoundException
```

là `true` trong nhánh đó. Các phương thức khả dụng trực tiếp trên biến `ex` vẫn bị giới hạn bởi kiểu tĩnh `IOException` trừ khi dùng pattern matching `instanceof` hoặc ép kiểu an toàn.

Ví dụ Java 17 về kiểm tra kiểu runtime (đặt trong handler):

```java
if (ex instanceof java.io.FileNotFoundException missing) {
    System.out.println("Missing file: " + missing.getMessage());
} else {
    System.out.println("Other I/O: " + ex.getMessage());
}
```

Đây là đoạn minh họa, cần biến `ex` là một `IOException` đã bắt. Pattern matching `instanceof` hỗ trợ ràng buộc biến `missing` khi đối tượng thật thuộc lớp con; tính năng này có sẵn trong Java 17.

Hãy phân nhánh theo subtype khi caller **thật sự có cách xử lý riêng**. Nếu lớp con không làm thay đổi phản ứng, một handler `IOException` có thể đủ. Không nên dùng `ex.getMessage().contains("file")` để suy ra subtype vì thông điệp không phải hợp đồng kiểu.

## 9. Có thể ném một loại ngoại lệ khác kiểu cha khai báo không?

Có, nhưng cần phân biệt **checked** và **unchecked**.

Giả sử:

```java
static void load(String path) throws java.io.IOException {
    if (path == null) {
        throw new IllegalArgumentException("path is required");
    }
    if ("missing".equals(path)) {
        throw new java.io.FileNotFoundException(path);
    }
}
```

Đây là phương thức minh họa:

- `FileNotFoundException` là checked và được bao phủ bởi `throws IOException`.
- `IllegalArgumentException` là unchecked, nên được phép ném mà không phải ghi trong `throws`.
- Một ngoại lệ checked **khác nhánh**, ví dụ `java.sql.SQLException`, sẽ yêu cầu thêm `throws SQLException` hoặc phải được bắt và xử lý trong phương thức. `throws IOException` không bao phủ `SQLException`.
- `Error` cũng không bị buộc khai báo nhưng không nên được xem là loại thất bại ứng dụng có thể phục hồi bình thường.

Vì vậy cụm “phương thức khai báo `throws IOException` nên chỉ có thể ném `IOException`” là **sai**. Diễn đạt chính xác hơn: **những checked exception được phép lan ra trong mã Java bình thường phải thỏa hợp đồng khai báo**, còn unchecked exceptions vẫn có thể xảy ra.

## 10. Nếu bọc (`wrap`) ngoại lệ con thì kiểu ngoài thay đổi

Đôi khi caller ở tầng trên cần lỗi ở mức trừu tượng khác. Ví dụ:

```java
static void loadRequiredConfiguration() {
    try {
        loadFile();
    } catch (java.io.FileNotFoundException cause) {
        throw new IllegalStateException(
                "Required configuration is missing", cause);
    } catch (java.io.IOException cause) {
        throw new IllegalStateException(
                "Required configuration cannot be read", cause);
    }
}
```

Đây là **phương thức minh họa**, giả định `loadFile()` có thể ném `IOException`. Khi bọc:

1. Ngoại lệ gốc có thể là `FileNotFoundException`, thuộc nhánh `IOException`.
2. Tầng hiện tại tạo **một đối tượng mới** `IllegalStateException` và truyền ngoại lệ gốc làm `cause`.
3. Caller phía ngoài nhận **kiểu thực tế của ngoại lệ mới** là `IllegalStateException`, không tự động đi vào `catch (IOException)`.
4. Nếu cần xem lỗi I/O sâu bên trong, caller hoặc hệ thống log kiểm tra `ex.getCause()` và chuỗi nguyên nhân. Không nên coi `catch` tự đi xuyên qua `cause` để tìm kiểu gốc: `catch` chỉ kiểm tra đối tượng đang được ném.

Việc bọc có thể đúng khi tầng ứng dụng chủ động chuyển từ lỗi I/O sang trạng thái không thể khởi tạo dịch vụ. Nhưng đừng bọc ở mọi tầng chỉ để thêm một câu “failed”; nó làm hợp đồng API thay đổi, có thể khiến handler chuyên biệt ở caller không còn bắt được lỗi qua kiểu trực tiếp.

### Ném lại cùng ngoại lệ thì sao?

`throw ex;` ném lại **cùng đối tượng** đã bắt. Thông thường kiểu runtime vẫn là kiểu ban đầu; không tạo wrapper mới. Với checked exceptions, khai báo của phương thức chứa lệnh ném lại vẫn phải thỏa quy tắc kiểm tra của trình biên dịch. Java có cơ chế phân tích kiểu chính xác hơn cho một số trường hợp ném lại biến `catch` không bị gán lại (*precise rethrow*), nhưng không nên suy ra rằng mọi kiểu checked có thể được ném lại mà không cần khai báo.

## 11. Khai báo nhiều ngoại lệ checked và lớp con của chúng

Một phương thức có thể công bố nhiều nhóm lỗi:

```java
static void process()
        throws java.io.IOException, java.sql.SQLException {
    // Có thể truy cập tệp hoặc cơ sở dữ liệu.
}
```

Đây là ví dụ về **chữ ký phương thức**, phần thân chưa triển khai thao tác thật.

- `throws IOException, SQLException` cho biết cả hai nhóm checked exception có thể đi ra ngoài.
- Một `FileNotFoundException` được bao phủ bởi `IOException`.
- Một lớp con của `SQLException` được bao phủ bởi `SQLException`.
- Caller có thể chọn hai `catch` riêng nếu cần hành động khác nhau, hoặc `catch (IOException | SQLException ex)` nếu chính sách xử lý giống nhau.
- `IOException` và `SQLException` không nằm trong quan hệ cha/con trực tiếp nên được dùng chung trong multi-catch.

Không cần liệt kê vừa `throws IOException` vừa `throws FileNotFoundException` để cho phép lớp con; kiểu cha đã bao phủ. Việc thêm tên lớp con đôi khi phục vụ tài liệu hóa nhưng thường thừa trong chữ ký; `@throws` của JavaDoc có thể mô tả chính xác hơn điều kiện khiến ngoại lệ con phát sinh.

## 12. `throws`, đa hình và khả năng thay thế triển khai

Nếu thư viện công khai:

```java
interface Storage {
    byte[] read(String key) throws java.io.IOException;
}
```

nhiều triển khai có thể ném các `IOException` cụ thể khác nhau khi thất bại. Caller dùng kiểu `Storage` vẫn có thể bắt một `IOException` và hoạt động với triển khai mới mà không buộc biên dịch lại logic xử lý từng subclass. Đây là lợi ích của một **hợp đồng ngoại lệ có mức trừu tượng ổn định**.

Tuy nhiên, chọn kiểu cha quá rộng như `throws Exception` chỉ để “linh hoạt” có thể đẩy quá nhiều trách nhiệm sang caller và làm mờ cách phục hồi. Nên thiết kế API quanh các **nhóm lỗi caller có thể xử lý hợp lý**, chứ không phơi toàn bộ chi tiết triển khai.

Cũng không nên hiểu rằng “throws ghi kiểu cha” đồng nghĩa với “caller không bao giờ cần biết kiểu con”. Caller có thể kiểm tra kiểu runtime hoặc bắt subclass khi có một phương án xử lý riêng cho trường hợp ấy.

### `throws` không tạo overload mới

Java không cho phép hai phương thức chỉ khác nhau ở mệnh đề `throws`:

```java
// Cố ý sai nếu đặt cả hai trong cùng một lớp:
void load() throws java.io.IOException {}
void load() throws java.io.FileNotFoundException {}
```

Hai khai báo có cùng tên và cùng danh sách tham số, nên không phải hai overload hợp lệ. Ngoại lệ checked trong `throws` ảnh hưởng kiểm tra hợp đồng và override, nhưng không phân biệt phương thức khi overload.

## 13. Những ngộ nhận và lỗi lập trình thường gặp

| Ngộ nhận | Điều đúng |
| --- | --- |
| `throws IOException` luôn tạo ra `IOException` | `throws` chỉ khai báo khả năng; phương thức có thể chạy thành công hoặc ném subclass |
| Nếu caller bắt `IOException` thì đối tượng `FileNotFoundException` bị biến thành `IOException` | Kiểu runtime không đổi; `getClass()` vẫn là `FileNotFoundException` |
| `throws FileNotFoundException` cho phép ném bất kỳ `IOException` nào | Không; khai báo subtype không bao phủ supertype |
| Có `throws IOException` thì không thể ném `IllegalStateException` | Có thể, vì `IllegalStateException` là unchecked |
| Bắt `FileNotFoundException` là đủ cho mọi phương thức `throws IOException` | Không nếu còn các `IOException` khác; caller phải xử lý/khai báo phần checked còn lại |
| Override có thể mở từ `throws IOException` sang `throws Exception` | Không, vì làm hợp đồng checked exception rộng hơn |
| `catch` tìm theo `getCause()` | Không; chỉ kiểu của đối tượng đang ném được dùng để chọn handler |
| `throws Exception` là cách tốt nhất để khỏi lo loại lỗi | Quá rộng thường làm API khó hiểu và caller bị buộc xử lý nhiều trường hợp |
| Để phát sinh `NumberFormatException` phải khai báo `throws NumberFormatException` | Không bắt buộc; đây là unchecked exception |
| `throws` chỉ có trong lớp triển khai, không tác động tới người gọi qua interface | Caller được kiểm tra theo chữ ký ở **kiểu tĩnh** mà nó gọi |

### Nhầm thứ tự `catch`

Với:

```java
try {
    load();
} catch (java.io.IOException ex) {
    // ...
} catch (java.io.FileNotFoundException ex) {
    // ...
}
```

Đây là **ví dụ cố ý sai** nếu hai nhánh ở cùng một `try`: handler `IOException` đã bắt luôn `FileNotFoundException`, nên handler lớp con bị che khuất và mã không biên dịch. Đảo thứ tự để kiểm tra lớp con trước.

### Nhầm kiểu khai báo với dữ liệu có thể tin cậy ở runtime

Có `throws IOException` không tự cho biết lỗi thực tế đến từ thiếu tệp, quyền truy cập, kết nối hay lỗi đọc. Đừng suy ra nguyên nhân kỹ thuật duy nhất từ kiểu cha. Dùng subtype thực tế, message, cause, stack trace và thông tin về thao tác để chẩn đoán, rồi chỉ báo điều đã được xác minh.

## 14. Bài tập tự kiểm tra

**Bài A.** `static void f() throws IOException { throw new FileNotFoundException(); }` có hợp lệ không?

**Có.** `FileNotFoundException` kế thừa `IOException`; kiểu checked thực tế được bao phủ bởi kiểu khai báo cha.

**Bài B.** `static void f() throws FileNotFoundException { throw new IOException(); }` có hợp lệ không?

**Không.** `IOException` rộng hơn `FileNotFoundException`; muốn ném nó ra ngoài cần khai báo `throws IOException` hoặc một supertype phù hợp, hay bắt và xử lý bên trong.

**Bài C.** Phương thức khai báo `throws IOException` nhưng ném `EOFException`. `catch (IOException)` có xử lý được không?

**Có.** Kiểu runtime là `EOFException`, một subclass của `IOException`. Handler kiểu cha khớp được.

**Bài D.** Một interface khai báo `throws IOException`; lớp triển khai ghi đè khai báo `throws FileNotFoundException`. Có hợp lệ không?

**Có.** Override thu hẹp loại checked exception. Caller qua biến interface vẫn được kiểm tra theo `throws IOException` của interface; caller qua lớp concrete thấy khai báo hẹp hơn.

**Bài E.** Phương thức khai báo `throws IOException` và có lệnh `throw new IllegalArgumentException("bad input")`. Có cần thêm `throws IllegalArgumentException` không?

**Không.** `IllegalArgumentException` là unchecked exception. Nó vẫn có thể bị bắt tại runtime bằng handler thích hợp.

**Bài F.** Caller bắt `IOException` và nhận một `FileNotFoundException`. Gọi `ex.getClass().getSimpleName()` trả về gì?

**`FileNotFoundException`.** Bắt qua lớp cha không đổi kiểu động.

**Bài G.** Tầng giữa bắt `FileNotFoundException` rồi `throw new IllegalStateException("cannot start", ex)`. Tầng ngoài chỉ có `catch (IOException)` có bắt được wrapper không?

**Không.** Ngoại lệ đang ném ra là `IllegalStateException`; `FileNotFoundException` nằm trong `cause`. Cần handler tương thích với kiểu wrapper hoặc thay đổi thiết kế hợp đồng.

## 15. Checklist khi đọc một lời gọi có `throws`

1. **Đọc chữ ký:** các checked exception nào được khai báo? Chúng là kiểu cha hay kiểu cụ thể?
2. **Xem đường thực thi:** câu `throw` nào hoặc API nào có thể ném subtype của kiểu khai báo?
3. **Kiểm tra caller:** đã bắt hoặc khai báo đầy đủ các checked exception theo kiểu tĩnh của lời gọi chưa?
4. **Đọc handler:** nhánh `catch` lớp con đã đứng trước lớp cha chưa? Handler có đang xử lý đúng loại lỗi và đúng chính sách không?
5. **Xét overriding:** lớp triển khai có thu hẹp/giữ nguyên hợp đồng checked exception của kiểu cha/interface không?
6. **Xét runtime:** ngoại lệ thực tế có đúng là subtype dự kiến không? Có unchecked exception hoặc wrapper làm thay đổi kiểu ở tầng ngoài không?
7. **Giữ thông tin chẩn đoán:** nếu phải bọc, chuyển `cause`; nếu không có lý do đổi hợp đồng, cân nhắc để nguyên ngoại lệ đi lên.

**Ghi nhớ:** `throws` cho trình biên dịch và người gọi biết **nhóm checked exception mà phương thức có thể để thoát ra**; `throw`/API tại runtime quyết định **đối tượng ngoại lệ cụ thể**. Một khai báo kiểu cha bao phủ các lớp con checked, còn `catch` được chọn theo kiểu thực tế của đối tượng và quan hệ kế thừa. Trong phương thức ghi đè, hợp đồng checked exception chỉ có thể giữ tương đương hoặc được thu hẹp, không được mở rộng làm phá vỡ kỳ vọng của caller.