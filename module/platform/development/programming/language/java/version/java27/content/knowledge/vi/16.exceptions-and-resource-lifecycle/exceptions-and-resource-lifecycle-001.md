# Exception, RuntimeException, Error và lựa chọn cách xử lý

Trong Java 27, ngoại lệ (*exception*) là cơ chế truyền thông tin về tình huống bất thường từ nơi phát sinh đến nơi có thể quyết định cách xử lý. Java không chỉ có một loại ngoại lệ: các kiểu kế thừa từ `Throwable` được chia thành nhóm **checked** và **unchecked**; trong đó `RuntimeException` và `Error` đều là unchecked nhưng có mục đích sử dụng rất khác nhau.

Hiểu đúng sự khác nhau giữa `Exception`, `RuntimeException` và `Error` giúp thiết kế API rõ ràng, tránh nuốt lỗi, bảo toàn nguyên nhân gốc và không làm rò rỉ tài nguyên khi thao tác thất bại. Bài học thuộc chương **Ngoại lệ và vòng đời tài nguyên** của module **Java 27 và các kiến thức liên quan**. Các ví dụ chỉ dựa trên cú pháp và API Java SE hiện hành; không dùng cơ chế xử lý lỗi đã lỗi thời.

**Nguyên tắc định hướng:** chỉ bắt ngoại lệ tại nơi có đủ thông tin và trách nhiệm để xử lý; nếu không thể khôi phục, hãy truyền tiếp hoặc chuyển đổi sang ngoại lệ phù hợp với ranh giới API, đồng thời giữ thông tin nguyên nhân.

## 1. Cây kế thừa Throwable: ba tên dễ nhầm

### 1.1. Cấu trúc cơ bản

Chỉ thể hiện những nhánh quan trọng đối với bài học:

~~~text
java.lang.Object
└── java.lang.Throwable
    ├── java.lang.Exception
    │   ├── java.io.IOException
    │   ├── java.sql.SQLException
    │   ├── java.lang.InterruptedException
    │   └── java.lang.RuntimeException
    │       ├── java.lang.IllegalArgumentException
    │       │   └── java.lang.NumberFormatException
    │       ├── java.lang.IllegalStateException
    │       ├── java.lang.NullPointerException
    │       └── java.lang.IndexOutOfBoundsException
    └── java.lang.Error
        ├── java.lang.OutOfMemoryError
        ├── java.lang.StackOverflowError
        ├── java.lang.LinkageError
        └── java.lang.AssertionError
~~~

Sơ đồ chỉ liệt kê một số lớp tiêu biểu; Java còn nhiều lớp ngoại lệ khác. Mọi object được `throw` trong mã Java đều phải thuộc `Throwable` hoặc subtype của nó.

Cần ghi nhớ:

- `Exception` là lớp cha của nhiều tình huống mà chương trình có thể muốn xử lý. **Không phải mọi `Exception` đều là checked**: `RuntimeException` là con của `Exception`.
- `RuntimeException` là nhánh của `Exception`, biểu thị các ngoại lệ **unchecked** thường xuất hiện khi giả định về đầu vào, trạng thái hoặc thao tác của chương trình không được đáp ứng. Tuy nhiên, một số runtime exception cũng có thể phát sinh từ tình huống bên ngoài chương trình.
- `Error` là nhánh **khác** trực tiếp dưới `Throwable`, không nằm dưới `Exception`. Nó biểu thị các lỗi mà chương trình thông thường không được kỳ vọng sẽ phục hồi.
- `Throwable` tự nó cũng thuộc nhóm **checked** theo quy tắc của JLS, trừ các nhánh `RuntimeException`, `Error` và subtype tương ứng.

### 1.2. Checked và unchecked được xác định bằng cây kiểu

| Kiểu | Checked / unchecked | Compiler yêu cầu `catch` hoặc `throws`? | Cách dùng điển hình |
|---|---|---|---|
| `IOException` | Checked | Có, khi phương thức có thể ném nó theo kiểm tra ngoại lệ | Đọc/ghi file, luồng I/O |
| `SQLException` | Checked | Có | Tương tác JDBC |
| `InterruptedException` | Checked | Có | Một số thao tác chặn khi thread bị interrupt |
| `Exception` | Checked | Có nếu khai báo/lan truyền kiểu này | Kiểu cha rộng của các ngoại lệ |
| `RuntimeException` | Unchecked | Không bắt buộc | Lỗi đầu vào, trạng thái, thao tác không hợp lệ |
| `IllegalArgumentException` | Unchecked | Không bắt buộc | Đối số không đáp ứng contract của phương thức |
| `NullPointerException` | Unchecked | Không bắt buộc | Dereference null hoặc một số API từ chối null |
| `Error` | Unchecked | Không bắt buộc | Nhóm lỗi thường không nên phục hồi trong logic ứng dụng |
| `OutOfMemoryError` | Unchecked | Không bắt buộc | JVM không đáp ứng được nhu cầu cấp phát bộ nhớ |
| `Throwable` | Checked | Có nếu khai báo/lan truyền trực tiếp | Lớp gốc, không nên là API lỗi nghiệp vụ thông thường |

**Unchecked không đồng nghĩa nhẹ, checked không đồng nghĩa nghiêm trọng.** Đây là quy tắc kiểm tra tại thời điểm biên dịch, không phải bảng xếp hạng độ nguy hiểm.

### 1.3. Phân loại theo quy tắc ngôn ngữ

Theo JLS §11.1.1:

- **Unchecked exception classes:** `RuntimeException` và mọi subtype của nó; `Error` và mọi subtype của nó.
- **Checked exception classes:** mọi lớp ngoại lệ còn lại kế thừa `Throwable`.

Vì thế, một lớp tự định nghĩa kế thừa trực tiếp `Exception` là **checked**; nếu kế thừa `RuntimeException` thì là **unchecked**. Không cần thêm từ khóa riêng để tuyên bố checked/unchecked.

## 2. Điều gì xảy ra khi một ngoại lệ được ném?

### 2.1. Truyền quyền điều khiển ra khỏi điểm phát sinh lỗi

Một ngoại lệ có thể được ném tường minh bằng `throw` hoặc phát sinh trong khi JVM/thư viện thực thi một phép toán.

~~~java
static int divide(int numerator, int denominator) {
    return numerator / denominator;
}

int value = divide(10, 0); // ArithmeticException
~~~

Khi phép chia nguyên với mẫu số bằng 0 phát sinh `ArithmeticException`, lời gọi không kết thúc bình thường bằng một giá trị trả về. JVM tìm một `catch` phù hợp trong luồng thực thi hiện tại. Nếu không có handler tại phương thức đang chạy, ngoại lệ tiếp tục lan ra caller và các lời gọi bên ngoài.

Sự lan truyền này không bảo đảm mọi câu lệnh tiếp theo đều chạy. Đó là lý do logic giải phóng tài nguyên cần được đặt trong `try`-with-resources hoặc, với tài nguyên không phù hợp cơ chế này, trong `finally`.

### 2.2. throw khác throws

`throw` là một **câu lệnh** ném một object:

~~~java
static void requirePositive(int quantity) {
    if (quantity <= 0) {
        throw new IllegalArgumentException("quantity must be positive");
    }
}
~~~

`throws` là một phần của **khai báo phương thức hoặc constructor**, dùng để mô tả kiểu ngoại lệ có thể lan ra caller:

~~~java
static String readText(java.nio.file.Path path)
        throws java.io.IOException {
    return java.nio.file.Files.readString(path);
}
~~~

Bảng phân biệt:

| Cú pháp | Vị trí | Ý nghĩa |
|---|---|---|
| `throw new IllegalArgumentException(...)` | Trong thân phương thức | Thực sự ném một object ngoại lệ khi nhánh đó được chạy |
| `throws IOException` | Trong chữ ký phương thức/constructor | Công bố khả năng phương thức hoàn thành bất thường với checked exception |
| `catch (IOException e)` | Sau một khối `try` | Bắt ngoại lệ tương thích để xử lý |
| `finally { ... }` | Sau `try` hoặc `try`-`catch` | Thực hiện logic cuối cùng khi điều khiển rời khối theo quy tắc Java |

Khai báo `throws IOException` không tự ném ngoại lệ. Một phương thức có thể khai báo `throws IOException` mà một lần thực thi cụ thể không gặp lỗi I/O.

### 2.3. Phương thức không cần khai báo unchecked exceptions

Ví dụ:

~~~java
static int parseCount(String input) {
    return Integer.parseInt(input);
}
~~~

`Integer.parseInt` có thể ném `NumberFormatException`, là subtype của `IllegalArgumentException` và `RuntimeException`. Compiler không buộc `parseCount` khai báo `throws NumberFormatException` hoặc bắt nó.

Có thể ghi `throws NumberFormatException` nhằm mô tả API, nhưng đây không phải yêu cầu compile-time. Trong thực tế, contract lỗi có thể được trình bày bằng Javadoc `@throws` và hướng dẫn sử dụng API.

## 3. Checked exception: buộc caller cân nhắc đường lỗi

### 3.1. Ví dụ với IOException

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

class FileReaderExample {
    static String load(Path path) throws IOException {
        return Files.readString(path);
    }
}
~~~

`Files.readString` có thể ném `IOException`. Nếu `load` không bắt ngoại lệ đó, `load` khai báo `throws IOException` để caller có thể tiếp tục truyền lỗi hoặc xử lý.

Một caller có thể bắt:

~~~java
static void show(java.nio.file.Path path) {
    try {
        String text = java.nio.file.Files.readString(path);
        System.out.println(text);
    } catch (java.io.IOException e) {
        System.err.println("Không thể đọc dữ liệu từ " + path);
    }
}
~~~

Ví dụ minh họa một nơi đã quyết định chuyển lỗi đọc file thành thông báo. Trong một dịch vụ thực tế, nếu việc đọc thất bại làm cho nghiệp vụ không thể tiếp tục, chỉ in thông báo rồi giả vờ thành công là không đủ; phải trả về trạng thái thất bại hoặc để lỗi lan lên tầng điều phối.

### 3.2. Catch hoặc declare

Một phương thức gọi API có checked exception có các lựa chọn hợp lệ về mặt biên dịch:

1. Bắt ngoại lệ trong `catch` phù hợp.
2. Khai báo `throws` để chuyển trách nhiệm sang caller.
3. Bắt rồi ném ngoại lệ khác, có thể là checked hoặc unchecked, theo contract của tầng hiện tại.

Ví dụ bắt rồi chuyển sang checked exception có ý nghĩa miền:

~~~java
final class ConfigurationLoadException extends Exception {
    ConfigurationLoadException(String message, Throwable cause) {
        super(message, cause);
    }
}

static String loadConfiguration(java.nio.file.Path path)
        throws ConfigurationLoadException {
    try {
        return java.nio.file.Files.readString(path);
    } catch (java.io.IOException e) {
        throw new ConfigurationLoadException(
                "Cannot load configuration: " + path, e);
    }
}
~~~

Cách bọc này **giữ nguyên cause** là `IOException`, thay vì xóa dấu vết lỗi gốc.

### 3.3. Khi nào checked exception phù hợp?

Checked exception là lựa chọn đáng cân nhắc khi:

- Sự cố nằm trong contract mà caller có thể được yêu cầu **nhận biết và xử lý**.
- Caller có hành động khôi phục hợp lý: chọn nguồn dữ liệu khác, yêu cầu nhập lại, thử phương án dự phòng hoặc báo kết quả thất bại rõ ràng.
- Việc bắt hoặc công bố lỗi tại ranh giới API giúp tránh bỏ sót một nhánh kết quả quan trọng.

Tuy nhiên, không nên tạo checked exception cho mọi lỗi. Nếu rất nhiều tầng trung gian chỉ việc viết thêm `throws` mà không có quyết định xử lý, hãy đánh giá lại ranh giới API và cách mô hình hóa lỗi. Checked/unchecked là công cụ thiết kế contract, không thay thế việc xác định trách nhiệm nghiệp vụ.

## 4. RuntimeException: unchecked không có nghĩa là có thể bỏ qua

### 4.1. Lỗi đối số và trạng thái

~~~java
static int percentage(int part, int total) {
    if (total <= 0) {
        throw new IllegalArgumentException("total must be positive");
    }
    if (part < 0 || part > total) {
        throw new IllegalArgumentException("part out of range");
    }
    return (int) (100L * part / total);
}
~~~

`IllegalArgumentException` diễn đạt rằng **caller vi phạm điều kiện đầu vào** của API. Kiểm tra đầu vào sớm giúp ngoại lệ có thông điệp chính xác hơn là để lỗi xảy ra sâu trong thuật toán.

`IllegalStateException` thường phù hợp khi thao tác được yêu cầu **không hợp lệ tại trạng thái hiện tại**:

~~~java
final class SingleUseToken {
    private boolean used;

    void consume() {
        if (used) {
            throw new IllegalStateException("Token already consumed");
        }
        used = true;
    }
}
~~~

Tuy vậy, trạng thái không hợp lệ có thể là một kết quả nghiệp vụ bình thường. Nếu ví dụ “token đã dùng” được hệ thống dự kiến xảy ra thường xuyên, bạn cũng có thể dùng kiểu kết quả minh bạch thay vì ném ngoại lệ. Lựa chọn phụ thuộc contract, không chỉ tên lớp ngoại lệ.

### 4.2. Một số runtime exception tiêu biểu

| Kiểu | Tình huống điển hình | Điều cần làm |
|---|---|---|
| `IllegalArgumentException` | Caller truyền giá trị không hợp lệ | Xác định precondition; kiểm tra đầu vào |
| `NumberFormatException` | Chuỗi không biểu diễn được số đúng cú pháp/phạm vi | Bắt tại nơi chuyển dữ liệu người dùng |
| `IllegalStateException` | Phương thức không dùng được ở trạng thái hiện tại | Sửa thứ tự thao tác hoặc mô hình trạng thái |
| `NullPointerException` | Truy cập null hoặc API chủ động từ chối null | Sửa hợp đồng null và nguồn gốc dữ liệu |
| `IndexOutOfBoundsException` | Chỉ số ngoài miền hợp lệ | Kiểm tra giới hạn và thuật toán |
| `UnsupportedOperationException` | API không hỗ trợ thao tác yêu cầu | Đổi thao tác hoặc contract collection |
| `UncheckedIOException` | Bọc một `IOException` ở tầng công bố unchecked | Xem lại cause và quyết định xử lý I/O |

**Không dùng `catch (RuntimeException e)` để che giấu tất cả vấn đề.** Nếu không có hành động phục hồi, giữ nguyên ngoại lệ để caller hoặc tầng xử lý lỗi biết thao tác đã thất bại.

### 4.3. Phân biệt input chưa hợp lệ và lỗi lập trình

Một chuỗi người dùng nhập không chuyển được sang số có thể là tình huống dự kiến trong giao diện nhập liệu, dù Java biểu diễn bằng `NumberFormatException` là unchecked.

Ví dụ chuyển nó thành một kiểu kết quả rõ ràng:

~~~java
static java.util.OptionalInt parsePort(String text) {
    if (text == null) {
        return java.util.OptionalInt.empty();
    }

    try {
        int port = Integer.parseInt(text);
        return port >= 1 && port <= 65535
                ? java.util.OptionalInt.of(port)
                : java.util.OptionalInt.empty();
    } catch (NumberFormatException e) {
        return java.util.OptionalInt.empty();
    }
}
~~~

Ở đây caller có thể kiểm tra giá trị có mặt hay không, thay vì dùng exception làm cơ chế điều khiển một luồng tương tác thường xuyên. Nếu ứng dụng cần phân biệt “không phải số” với “số ngoài khoảng”, nên thiết kế kiểu kết quả có mã lỗi hoặc lý do thất bại riêng, không chỉ dùng `OptionalInt.empty()`.

## 5. Error: nhóm unchecked không dùng cho lỗi nghiệp vụ thông thường

### 5.1. Error nằm ngoài Exception

`Error` là sibling của `Exception` dưới `Throwable`. Vì vậy:

~~~java
try {
    doWork();
} catch (Exception e) {
    // Không bắt các đối tượng thuộc nhánh Error.
}
~~~

`catch (Exception e)` bắt các subtype của `Exception`, bao gồm `RuntimeException`, nhưng **không** bắt `Error` hoặc subclass của `Error`.

### 5.2. Những trường hợp tiêu biểu

- `OutOfMemoryError`: môi trường chạy không thể đáp ứng nhu cầu cấp phát.
- `StackOverflowError`: luồng thực thi vượt quá khả năng stack, thường do đệ quy quá sâu hoặc vô hạn.
- `LinkageError` và các subtype: lỗi liên quan đến liên kết hoặc tải lớp.
- `AssertionError`: thất bại của một assertion được kích hoạt hoặc do mã tường minh ném.

Những sự cố này không đồng nhất về nguồn gốc hay cách vận hành, nhưng chúng đều thuộc nhánh `Error` và là unchecked. Không nên coi `Error` là một cách đặt tên “lỗi nghiêm trọng hơn” cho validation của ứng dụng.

### 5.3. Có nên bắt Error hoặc Throwable?

Trong business logic thông thường: **không**. Việc bắt `Error` hay `Throwable` rồi cố tiếp tục có thể để chương trình vận hành trong trạng thái không đáng tin cậy; thậm chí việc ghi log hoặc tạo thông điệp mới cũng có thể thất bại khi tài nguyên hệ thống cạn kiệt.

Một số runtime/container/framework ở **ranh giới rất đặc biệt** có thể quan sát hoặc bắt `Throwable` nhằm ghi nhận sự cố, thực hiện cleanup tối thiểu hoặc cô lập một tác vụ, nhưng cần thiết kế và kiểm tra riêng. Điều này **không** biến `catch (Throwable)` thành cách xử lý ngoại lệ thông dụng.

Nếu không có handler thích hợp, ngoại lệ không được bắt sẽ được chuyển đến cơ chế xử lý ngoại lệ chưa bắt của thread. Không nên khẳng định rằng **mọi** ngoại lệ không được bắt đều làm cả JVM kết thúc ngay; hậu quả phụ thuộc thread, entry point và cơ chế vận hành.

## 6. Lựa chọn catch, propagate, translate hoặc return result

### 6.1. Ma trận quyết định

| Tình huống | Cách xử lý thường phù hợp | Lý do |
|---|---|---|
| Đối số API vi phạm precondition | Ném `IllegalArgumentException` hoặc kiểu unchecked cụ thể | Caller cần sửa cách sử dụng API |
| Trạng thái object không cho phép thao tác | Ném `IllegalStateException` hoặc kiểu miền phù hợp | Hợp đồng trạng thái rõ ràng |
| Đọc dữ liệu thất bại và caller có thể quyết định | Khai báo `throws IOException` hoặc checked exception có ngữ nghĩa tầng hiện tại | Caller được buộc xem xét đường lỗi |
| Lỗi I/O xảy ra trong API không thể khai báo checked | Bọc bằng `UncheckedIOException` khi phù hợp | Giữ cause, không xuyên thủng contract của API |
| Đầu vào người dùng không hợp lệ thường xuyên | Trả kiểu kết quả/validation có cấu trúc hoặc bắt tại ranh giới chuyển đổi | Tránh dùng ngoại lệ làm luồng bình thường |
| Sự cố tạm thời khi gọi hệ thống ngoài | Catch cụ thể, retry có giới hạn nếu an toàn và có chính sách | Phục hồi cần điều kiện, không phải retry tất cả |
| `InterruptedException` | Truyền tiếp; hoặc khôi phục interrupt flag nếu không truyền tiếp | Tôn trọng tín hiệu hủy/ngắt |
| `Error` từ JVM | Thường để lan ra ranh giới vận hành | Ứng dụng thường không đủ điều kiện phục hồi |
| Ngoại lệ không thể phục hồi ở tầng hiện tại | Để lan tiếp, có thể chuyển đổi ở ranh giới abstraction | Không giả vờ thao tác thành công |

Đây là hướng dẫn thiết kế, **không phải quy tắc compiler áp đặt**. Cùng một `IOException` có thể được truyền tiếp ở tầng thư viện nhưng được chuyển thành HTTP response, thông báo người dùng hoặc trạng thái job thất bại ở tầng trên.

### 6.2. Cây quyết định đơn giản

~~~mermaid
flowchart TD
    A[Phát sinh tình huống bất thường] --> B{Đây là Error từ JVM?}
    B -->|Thường có| C[Không bắt trong business logic]
    B -->|Không| D{Đây là kết quả nghiệp vụ dự kiến?}
    D -->|Có| E[Ưu tiên result/validation rõ ràng]
    D -->|Không| F{Tầng hiện tại có thể phục hồi đúng?}
    F -->|Có| G[Bắt đúng kiểu, phục hồi có kiểm soát]
    F -->|Không| H{Có ranh giới abstraction cần chuyển đổi?}
    H -->|Có| I[Bọc ngoại lệ, giữ nguyên cause]
    H -->|Không| J[Propagate cho caller]
~~~

Câu hỏi quan trọng nhất khi viết `catch` là: “**Sau catch, chương trình sẽ làm gì để bảo đảm hợp đồng của thao tác này vẫn đúng?**” Nếu câu trả lời chỉ là “in log rồi tiếp tục”, handler có thể đang che giấu thất bại.

### 6.3. Propagate: để caller quyết định

~~~java
static String readSettings(java.nio.file.Path file)
        throws java.io.IOException {
    return java.nio.file.Files.readString(file);
}
~~~

Đây là lựa chọn phù hợp nếu `readSettings` chỉ biết cách đọc, còn caller mới biết fallback hợp lý.

### 6.4. Translate: đổi loại lỗi ở ranh giới abstraction

~~~java
static String loadBusinessRules(java.nio.file.Path file) {
    try {
        return java.nio.file.Files.readString(file);
    } catch (java.io.IOException e) {
        throw new java.io.UncheckedIOException(
                "Cannot load business rules from " + file, e);
    }
}
~~~

`UncheckedIOException` hiện hành dùng để bọc `IOException` dưới dạng unchecked. Vì `e` vẫn là cause, caller và hệ thống quan sát có thể điều tra nguyên nhân gốc.

Không bọc vô điều kiện mọi checked exception thành `RuntimeException` chỉ để loại bỏ `throws`. Hãy chuyển đổi khi contract tầng hiện tại cần abstraction khác và cần truyền đạt thất bại rõ ràng.

### 6.5. Recover: bắt và thực sự xử lý được

~~~java
static String loadOrDefault(java.nio.file.Path path,
                            String defaultValue) {
    try {
        return java.nio.file.Files.readString(path);
    } catch (java.nio.file.NoSuchFileException e) {
        // Quy tắc nghiệp vụ: file tùy chọn không tồn tại thì dùng mặc định.
        return defaultValue;
    } catch (java.io.IOException e) {
        throw new java.io.UncheckedIOException(
                "Failed to read optional configuration", e);
    }
}
~~~

Ở đây chỉ `NoSuchFileException` có chính sách fallback. Các lỗi I/O khác như không có quyền truy cập hoặc lỗi đĩa không được đánh đồng với “file không tồn tại”.

Nếu file không tồn tại thực sự là lỗi nghiêm trọng, **không** nên dùng fallback này. Ý nghĩa nghiệp vụ quyết định handler, không chỉ tên ngoại lệ.

## 7. Catch đúng kiểu và đúng thứ tự

### 7.1. Bắt subtype trước supertype

Các nhánh `catch` được xét theo thứ tự mã nguồn. Nếu bắt một supertype trước subtype thì nhánh sau có thể không bao giờ được chọn và sẽ bị compiler từ chối.

~~~java
static void handle(java.nio.file.Path file) {
    try {
        java.nio.file.Files.readString(file);
    } catch (java.nio.file.NoSuchFileException e) {
        System.err.println("File does not exist");
    } catch (java.io.IOException e) {
        System.err.println("Other I/O failure");
    }
}
~~~

`NoSuchFileException` là subclass của `IOException`. Vì vậy, subtype được bắt trước.

Ví dụ sai thứ tự:

~~~java
// Không hợp lệ: nhánh NoSuchFileException đã bị IOException che khuất.
// try {
//     read();
// } catch (IOException e) {
//     ...
// } catch (NoSuchFileException e) {
//     ...
// }
~~~

### 7.2. Multi-catch cho cách xử lý giống nhau

~~~java
static void parseAndRead(String text, java.nio.file.Path file) {
    try {
        int count = Integer.parseInt(text);
        String data = java.nio.file.Files.readString(file);
        System.out.println(data.repeat(count));
    } catch (NumberFormatException | java.io.IOException e) {
        System.err.println("Input or read failure: " + e.getMessage());
    }
}
~~~

Các kiểu trong multi-catch phải là những lựa chọn không có quan hệ subtype trực tiếp khiến một lựa chọn bao phủ lựa chọn khác. Biến catch của multi-catch là effectively final và không được gán lại.

Ví dụ này chỉ minh họa cú pháp; trong sản phẩm, lỗi parse và lỗi I/O thường có hướng phục hồi khác nhau nên có thể cần tách thành hai `catch`.

### 7.3. Hạn chế catch Exception ở sâu trong hệ thống

~~~java
// Thiết kế dễ che giấu lỗi nếu không có chính sách thật:
try {
    executeOperation();
} catch (Exception e) {
    System.err.println("Something went wrong");
    // Tiếp tục như thể thao tác thành công.
}
~~~

`catch (Exception)` có thể chặn nhiều loại lỗi lập trình thuộc `RuntimeException`, làm khó phát hiện bug. Ở một ranh giới ứng dụng (ví dụ job runner), việc bắt rộng để báo **kết quả thất bại** và cô lập một task đôi khi hợp lý; nhưng đó là khác biệt với việc nuốt lỗi rồi trả kết quả thành công.

Không cần bắt mọi lỗi ở mọi tầng. Các thư viện thường để ngoại lệ lan truyền, còn entry point hoặc boundary chuyển chúng thành phản hồi vận hành phù hợp.

## 8. Giữ nguyên nguyên nhân gốc, stack trace và ngữ cảnh

### 8.1. Không làm mất cause

**Không nên:**

~~~java
try {
    performIo();
} catch (java.io.IOException e) {
    throw new IllegalStateException("Failed");
}
~~~

Lỗi gốc `IOException` không được giữ dưới dạng cause, khiến quá trình điều tra khó hơn.

**Nên:**

~~~java
try {
    performIo();
} catch (java.io.IOException e) {
    throw new IllegalStateException("Failed to process input", e);
}
~~~

`Throwable.getCause()` trả về nguyên nhân nếu có; chain có thể gồm nhiều tầng và được hiển thị trong stack trace.

Hai snippet trên giả định `performIo()` là phương thức có thể ném `IOException`. Khi viết mã thật, chỉ bắt những checked exception mà khối `try` có thể ném theo kiểm tra của compiler.

### 8.2. Thông tin nên ghi vào message

Thông điệp nên giúp nhận diện thao tác thất bại và ngữ cảnh an toàn, chẳng hạn tên thao tác, loại dữ liệu, mã yêu cầu hoặc tên nguồn đã được xử lý phù hợp.

Tránh nhúng mật khẩu, token, chuỗi kết nối chứa bí mật hoặc dữ liệu cá nhân nhạy cảm vào exception message và log. Stack trace có thể được gửi tới hệ thống giám sát hoặc lưu lâu dài.

### 8.3. Log tại ranh giới có trách nhiệm

Nếu tầng thấp vừa log lỗi vừa ném tiếp, còn ba tầng cao cũng log cùng lỗi, hệ thống có thể tạo nhiều bản ghi trùng nhau cho một sự cố.

Một định hướng hữu ích:

- Tầng thấp **bổ sung ngữ cảnh và giữ cause** khi chuyển đổi.
- Tầng quyết định lỗi không thể xử lý tiếp **ghi nhận kết quả thất bại**, có thể log stack trace một lần tại boundary.
- Những nơi phục hồi thành công chỉ ghi log theo chính sách vận hành, không báo sự cố thất bại nếu kết quả cuối đã đúng.

Không coi “log một lần” là luật tuyệt đối cho mọi kiến trúc; metrics/tracing và log nghiệp vụ có mục tiêu khác nhau. Điều quan trọng là mỗi bản ghi có ý nghĩa, không che giấu hay nhân bản thông tin lỗi.

### 8.4. Rethrow và stack trace

Nếu chỉ cần cho caller tiếp tục xử lý, có thể **không bắt**, hoặc bắt để thêm một hành động cần thiết rồi `throw e;`:

~~~java
static void run(java.nio.file.Path path)
        throws java.io.IOException {
    try {
        java.nio.file.Files.readString(path);
    } catch (java.io.IOException e) {
        // Có thể tăng metric thất bại tại đây nếu thật sự cần.
        throw e;
    }
}
~~~

`throw e;` ném lại object đang bắt, không tạo một exception mới. Nếu chọn bọc ngoại lệ để đổi tầng abstraction, nên truyền `e` làm cause thay vì chỉ lấy `e.getMessage()`.

## 9. Tự định nghĩa checked và unchecked exception

### 9.1. Custom checked exception

~~~java
final class MissingConfigurationException extends Exception {
    MissingConfigurationException(String key) {
        super("Missing configuration key: " + key);
    }

    MissingConfigurationException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Một API yêu cầu caller quyết định khi thiếu cấu hình có thể khai báo:

~~~java
static String requiredSetting(
        java.util.Map<String, String> values, String key)
        throws MissingConfigurationException {

    String value = values.get(key);
    if (value == null) {
        throw new MissingConfigurationException(key);
    }
    return value;
}
~~~

Trong ví dụ, việc thiếu một khóa bắt buộc được mô hình hóa bằng checked exception để caller phải xử lý hoặc khai báo. Một sản phẩm cụ thể cũng có thể chọn cấu hình thiếu là lỗi khởi tạo unchecked; đây là **quyết định contract**, không phải bắt buộc của Java.

### 9.2. Custom unchecked exception

~~~java
final class UnsupportedWorkflowStateException
        extends RuntimeException {

    UnsupportedWorkflowStateException(String state) {
        super("Unsupported workflow state: " + state);
    }
}
~~~

Custom unchecked exception phù hợp khi API cần phân biệt một nhóm sai hợp đồng/trạng thái cụ thể để caller có thể nhận diện, nhưng không muốn compiler buộc catch/declare.

Không nên tạo subclass riêng chỉ để đổi câu chữ của mọi ngoại lệ. Nếu một lớp hiện hành như `IllegalArgumentException` đã thể hiện đúng lỗi, dùng nó thường rõ và nhẹ hơn.

### 9.3. Không kế thừa Error để báo thất bại nghiệp vụ

~~~java
// Không nên dùng Error cho validation/không đủ số dư:
// class InvalidBalanceError extends Error { }
~~~

Một hệ thống quản lý giao dịch cần mô hình hóa không đủ số dư bằng lỗi nghiệp vụ hoặc result thích hợp, không làm nó trông giống lỗi nghiêm trọng thuộc nhánh `Error` của nền tảng.

## 10. try, finally và try-with-resources

Bài thuộc chương vòng đời tài nguyên vì xử lý ngoại lệ không chỉ là chọn handler. Khi một thao tác thất bại, file handle, socket, stream hoặc transaction vẫn cần được đóng hay hoàn tất đúng hợp đồng.

### 10.1. finally không phải cơ chế đóng tài nguyên tối ưu cho mọi trường hợp

`finally` được thực thi khi luồng điều khiển rời một cấu trúc `try` theo các quy tắc của ngôn ngữ, kể cả khi phát sinh ngoại lệ hoặc `return` thông thường. Nhưng nó **không** được bảo đảm chạy nếu JVM bị dừng cưỡng bức, tiến trình kết thúc bất thường hoặc môi trường thực thi không tiếp tục.

Một đoạn có thể tạo bug:

~~~java
static int wrong() {
    try {
        return 10;
    } finally {
        return 20; // che mất kết quả trước đó
    }
}
~~~

Cũng vậy, một exception phát sinh từ `finally` có thể che ngoại lệ đang lan ra từ `try`. Vì vậy, tránh `return` trong `finally` và không dùng `finally` để bọc thao tác đóng `AutoCloseable` theo cách thủ công khi có thể dùng `try`-with-resources.

### 10.2. try-with-resources và AutoCloseable

Tài nguyên triển khai `AutoCloseable` có thể được khai báo ở phần header của `try`:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

class FirstLineReader {
    static String firstLine(Path path) throws IOException {
        try (BufferedReader reader =
                     Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
            return reader.readLine();
        }
    }
}
~~~

Khi rời khối `try`, Java tự gọi `close()`, kể cả khi đang có exception. Thao tác đóng xảy ra theo **thứ tự ngược** thứ tự khởi tạo tài nguyên.

Với `try`-with-resources, nếu cả thân `try` và `close()` cùng ném exception, exception từ thân `try` thường là **primary**; exception từ `close()` được lưu dưới dạng **suppressed**. Có thể xem bằng `getSuppressed()`.

### 10.3. Ví dụ suppressed exception độc lập

Ví dụ dưới đây chỉ mô phỏng resource để dễ quan sát, không mở file thật:

~~~java
import java.io.IOException;

public class SuppressedDemo {

    static final class DemoResource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("close failed");
        }
    }

    public static void main(String[] args) {
        try (DemoResource ignored = new DemoResource()) {
            throw new IOException("work failed");
        } catch (IOException e) {
            System.out.println(e.getMessage()); // work failed

            for (Throwable suppressed : e.getSuppressed()) {
                System.out.println(suppressed.getMessage());
                // close failed
            }
        }
    }
}
~~~

Ở đây `IOException("work failed")` là primary exception. Khi đóng tài nguyên, `close()` ném một `IOException` khác và Java liên kết nó vào ngoại lệ chính dưới dạng suppressed.

**Cause và suppressed khác nhau:**

- `cause` mô tả ngoại lệ **dẫn tới** ngoại lệ hiện tại (ví dụ bọc `IOException` trong `UncheckedIOException`).
- `suppressed` ghi nhận các ngoại lệ khác phải giữ lại **đồng thời**, ví dụ lỗi đóng tài nguyên trong khi lỗi chính đã xảy ra.

### 10.4. Nhiều tài nguyên đóng ngược thứ tự

~~~java
try (
        FirstResource first = openFirst();
        SecondResource second = openSecond()
) {
    use(first, second);
}
~~~

Ví dụ trên mang tính cấu trúc: `FirstResource`, `SecondResource`, `openFirst`, `openSecond` và `use` là các kiểu/phương thức giả định. Nếu cả hai tài nguyên được tạo thành công, `second.close()` được gọi trước `first.close()` khi rời khối.

Nếu khởi tạo tài nguyên thứ hai thất bại, tài nguyên thứ nhất đã mở sẽ được đóng theo quy tắc `try`-with-resources. Hành vi này giúp giảm nguy cơ rò rỉ khi chuỗi khởi tạo dừng giữa chừng.

### 10.5. Resource có sẵn và effectively final

Java hiện hành cho phép sử dụng biến `final` hoặc *effectively final* có sẵn trong resource specification:

~~~java
java.io.BufferedReader reader =
        java.nio.file.Files.newBufferedReader(path);

try (reader) {
    System.out.println(reader.readLine());
}
~~~

Đoạn này giả định `path` là một `Path` hợp lệ trong cùng phạm vi và method xử lý `IOException`. `reader` không được gán lại sau khi khởi tạo để giữ tính effectively final. Tính năng này đã là một phần ổn định của ngôn ngữ, không phải cú pháp Preview.

### 10.6. AutoCloseable và Closeable khác nhau

- `AutoCloseable.close()` được khai báo với `throws Exception`. Từng implementation có thể giới hạn kiểu lỗi cụ thể hơn.
- `java.io.Closeable` là subtype của `AutoCloseable` với `close() throws IOException`.

Vì vậy, một biến có kiểu tĩnh `AutoCloseable` có thể buộc caller xử lý `Exception` rộng hơn so với một API cụ thể khai báo `Closeable`/`IOException`. Khi thiết kế interface tài nguyên, hãy chọn loại exception của `close` phù hợp để không đẩy checked exception quá rộng ra người dùng.

## 11. InterruptedException: đừng làm mất tín hiệu ngắt

### 11.1. Ý nghĩa đặc biệt

`InterruptedException` là checked exception được một số thao tác chặn ném khi thread bị ngắt, ví dụ `Thread.sleep`. Đây thường là tín hiệu điều phối về hủy/ngắt công việc, không chỉ là một lỗi kỹ thuật nên bỏ qua.

Một số phương thức chặn khi ném `InterruptedException` sẽ xóa interrupted status. Vì vậy, nếu code bắt rồi tiếp tục mà không truyền lại thông tin, tín hiệu ngắt có thể bị mất.

### 11.2. Cách ưu tiên: propagate khi contract cho phép

~~~java
static void waitBriefly() throws InterruptedException {
    Thread.sleep(100);
}
~~~

Nếu tầng hiện tại có thể khai báo `throws InterruptedException`, truyền tiếp giúp caller quyết định chính sách hủy tác vụ.

### 11.3. Nếu không thể propagate: restore interrupt flag

~~~java
static void waitWithoutCheckedThrow() {
    try {
        Thread.sleep(100);
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        return;
    }
}
~~~

`Thread.currentThread().interrupt()` đặt lại trạng thái interrupt. Sau đó, method kết thúc thay vì vô tình tiếp tục công việc mà hệ thống muốn ngừng.

Nếu API buộc phải ném loại exception khác, hãy cân nhắc **vừa khôi phục interrupt flag vừa giữ cause**, sau đó thực hiện chính sách kết thúc thích hợp:

~~~java
static void waitOrFail() {
    try {
        Thread.sleep(100);
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        throw new IllegalStateException("Operation interrupted", e);
    }
}
~~~

Không nên viết một `catch (InterruptedException e)` trống. Tránh gọi `Thread.interrupted()` chỉ để “kiểm tra” tín hiệu trong handler khi không hiểu rằng phương thức tĩnh này **xóa** trạng thái interrupt của thread hiện tại.

## 12. Ví dụ hoàn chỉnh: contract checked và unchecked

Tạo file `ExceptionDecisionsDemo.java`. Ví dụ này không cần file, mạng, database hoặc framework bên ngoài; có thể chạy với Java SE hiện hành.

~~~java
import java.util.List;
import java.util.Map;

public final class ExceptionDecisionsDemo {

    static final class MissingSettingException extends Exception {
        MissingSettingException(String key) {
            super("Missing setting: " + key);
        }
    }

    static String required(Map<String, String> settings, String key)
            throws MissingSettingException {

        String value = settings.get(key);
        if (value == null) {
            throw new MissingSettingException(key);
        }
        return value;
    }

    static int parsePositiveLimit(String text) {
        final int result;

        try {
            result = Integer.parseInt(text);
        } catch (NumberFormatException e) {
            throw new IllegalArgumentException(
                    "limit must be a decimal integer", e);
        }

        if (result <= 0) {
            throw new IllegalArgumentException(
                    "limit must be greater than zero");
        }

        return result;
    }

    static void run(Map<String, String> settings)
            throws MissingSettingException {

        String rawLimit = required(settings, "limit");
        int limit = parsePositiveLimit(rawLimit);

        System.out.println("Accepted limit: " + limit);
    }

    public static void main(String[] args) {
        List<Map<String, String>> cases = List.of(
                Map.of("limit", "5"),
                Map.of("limit", "-2"),
                Map.of("limit", "not-a-number"),
                Map.of()
        );

        for (Map<String, String> settings : cases) {
            try {
                run(settings);
            } catch (MissingSettingException e) {
                System.out.println("Config missing: " + e.getMessage());
            } catch (IllegalArgumentException e) {
                System.out.println("Invalid config: " + e.getMessage());
                if (e.getCause() != null) {
                    System.out.println("Cause: "
                            + e.getCause().getClass().getSimpleName());
                }
            }
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ExceptionDecisionsDemo.java
java ExceptionDecisionsDemo
~~~

Diễn giải:

1. Cấu hình `limit=5` được xử lý thành công.
2. `limit=-2` là giá trị số nhưng vi phạm precondition nghiệp vụ; `parsePositiveLimit` ném `IllegalArgumentException`.
3. `limit=not-a-number` làm `Integer.parseInt` ném `NumberFormatException`; phương thức bọc nó thành `IllegalArgumentException` và giữ cause.
4. Cấu hình thiếu `limit` tạo `MissingSettingException` (checked) để caller xử lý riêng.
5. `main` nằm ở ranh giới chạy demo, nên quyết định cách hiển thị các loại thất bại. Trong hệ thống sản phẩm, có thể thay việc in ra console bằng trạng thái tác vụ, HTTP response hoặc log có cấu trúc.

Mục tiêu của ví dụ là minh họa **cách thiết kế contract khác nhau**, không khẳng định “thiếu cấu hình” bắt buộc luôn là checked exception trong mọi hệ thống.

## 13. Những lỗi thiết kế thường gặp

| Sai lầm | Tác hại | Cách cải thiện |
|---|---|---|
| `catch (Exception e) { }` | Nuốt thất bại, thao tác có vẻ thành công | Chỉ catch khi có cách xử lý thực sự; nếu không thì propagate |
| `catch (Throwable e)` trong business logic | Có thể chặn cả `Error`, làm việc tiếp trong trạng thái nguy hiểm | Bắt các exception cụ thể |
| Bọc lỗi bằng `new RuntimeException(e.getMessage())` | Mất cause và stack trace gốc | Dùng constructor nhận `cause` |
| Bắt `IOException` rồi luôn trả chuỗi rỗng | Không phân biệt dữ liệu rỗng với đọc thất bại | Dùng kết quả có trạng thái hoặc ném lại |
| Retry mọi loại lỗi | Lặp lại lỗi không thể khôi phục, nhân đôi side effect | Chỉ retry lỗi tạm thời, giới hạn số lần và bảo đảm an toàn |
| `return` trong `finally` | Che kết quả hoặc ngoại lệ từ `try` | Tránh return trong finally |
| Đóng tài nguyên thủ công mà bỏ lỗi từ close | Dễ rò rỉ hoặc mất lỗi chính | Dùng try-with-resources |
| Chỉ log rồi throw cùng lỗi ở nhiều tầng | Log trùng, nhiễu điều tra | Ranh giới chịu trách nhiệm ghi nhận thất bại |
| Dùng `Error` cho dữ liệu không hợp lệ | Làm sai ngữ nghĩa của phân cấp Throwable | Dùng result hoặc exception thích hợp |
| Bắt `InterruptedException` rồi bỏ qua | Mất tín hiệu ngắt | Rethrow hoặc restore interrupt flag |
| Cho rằng unchecked là vô hại | Lỗi có thể lan xa hoặc làm thất bại tác vụ | Có contract, quan sát và test đường lỗi |
| Bắt mọi runtime exception để báo “input sai” | Che bug của ứng dụng dưới dạng lỗi người dùng | Chỉ chuyển những lỗi đầu vào đã xác định |
| Trả success sau khi một bước bắt buộc thất bại | Vi phạm contract nghiệp vụ | Propagate hoặc trả failure rõ ràng |

## 14. Checklist khi thiết kế một đường xử lý lỗi

Trước khi chốt API:

1. **Xác định nguồn gốc:** đầu vào không hợp lệ, trạng thái không hợp lệ, môi trường ngoài, hủy/ngắt hay lỗi nền tảng?
2. **Định nghĩa contract:** caller cần phân biệt loại thất bại nào để hành động?
3. **Chọn checked/unchecked một cách nhất quán:** quyết định dựa trên trách nhiệm caller và khả năng phục hồi, không chỉ độ nghiêm trọng.
4. **Bắt ngoại lệ đủ hẹp:** ưu tiên lớp cụ thể và chỉ tại điểm có chính sách xử lý.
5. **Giữ nguyên cause:** khi chuyển đổi lỗi, dùng constructor nhận `Throwable`/cause phù hợp.
6. **Không che lỗi:** không trả kết quả thành công giả, không catch trống, không lạm dụng fallback.
7. **Quản lý tài nguyên:** dùng try-with-resources cho `AutoCloseable` và kiểm tra suppressed khi điều tra lỗi đóng.
8. **Tôn trọng cancellation:** không nuốt `InterruptedException`.
9. **Xử lý ở boundary:** chuyển lỗi thành trạng thái phản hồi, sự kiện job, log hoặc metric hợp lý.
10. **Kiểm thử đường lỗi:** kiểm tra exception type, message/cause quan trọng, cleanup và trạng thái hệ thống sau thất bại.

## 15. Câu hỏi tự kiểm tra

1. Vì sao `RuntimeException` là subtype của `Exception` nhưng compiler không buộc bắt hay khai báo?
2. `catch (Exception e)` có bắt `OutOfMemoryError` không? Vì sao?
3. `IOException` và `IllegalArgumentException` có cùng cách kiểm tra compile-time không?
4. Khác biệt giữa `throw` và `throws` là gì?
5. Khi nào truyền tiếp `IOException` hợp lý hơn bọc nó trong `UncheckedIOException`?
6. Vì sao ném `new RuntimeException(e.getMessage())` có thể làm mất thông tin quan trọng?
7. Tại sao `NoSuchFileException` nên đứng trước `IOException` trong chuỗi `catch`?
8. Một giá trị người dùng nhập sai số có luôn cần được ném thành exception ra khỏi tầng giao diện không?
9. Vì sao `Error` không phù hợp để diễn đạt “không đủ số dư”?
10. Nếu thân `try` và `close` cùng ném exception trong try-with-resources, ngoại lệ nào là primary và tìm ngoại lệ còn lại ở đâu?
11. Vì sao `return` trong `finally` là một rủi ro?
12. Khi bắt `InterruptedException` mà không thể `throws` tiếp, cần làm gì để tránh mất tín hiệu ngắt?
13. Sau khi `catch`, yếu tố gì quyết định nên phục hồi, ném lại hay trả failure result?
14. Trong `ExceptionDecisionsDemo`, tại sao thiếu `limit` là checked exception nhưng giá trị `limit=-2` là unchecked? Đó có phải quy tắc bắt buộc cho mọi chương trình?

## 16. Tài liệu tham khảo chính thức

- [Java Language Specification, Java SE 27 — Chapter 11: Exceptions](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-11.html): phân loại ngoại lệ, checked/unchecked, kiểm tra lúc biên dịch và xử lý lúc chạy.
- [JLS §11.1.1 — The Kinds of Exceptions](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-11.html#jls-11.1.1): `Throwable`, `Exception`, `RuntimeException`, `Error` và phân loại checked/unchecked.
- [JLS §11.2 — Compile-Time Checking of Exceptions](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-11.html#jls-11.2): quy tắc catch/declare.
- [JLS §14.18 — The throw Statement](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-14.html#jls-14.18): câu lệnh `throw`.
- [JLS §14.20 — The try Statement](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-14.html#jls-14.20): `try`, `catch` và `finally`.
- [JLS §14.20.3 — try-with-resources](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-14.html#jls-14.20.3): đóng tài nguyên, thứ tự đóng và suppressed exception.
- [Java SE 27 API — Throwable](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Throwable.html): message, cause, stack trace và suppressed exceptions.
- [Java SE 27 API — Exception](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Exception.html): lớp cha của nhóm exception ứng dụng có thể xử lý.
- [Java SE 27 API — RuntimeException](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/RuntimeException.html): lớp cha của các runtime exception.
- [Java SE 27 API — Error](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Error.html): ngữ nghĩa của nhánh Error.
- [Java SE 27 API — AutoCloseable](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/AutoCloseable.html): contract `close()` và try-with-resources.
- [Java SE 27 API — UncheckedIOException](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/io/UncheckedIOException.html): bọc `IOException` thành unchecked có cause.
- [Java SE 27 API — InterruptedException](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/InterruptedException.html): truyền tiếp ngoại lệ hoặc khôi phục interrupt flag.
