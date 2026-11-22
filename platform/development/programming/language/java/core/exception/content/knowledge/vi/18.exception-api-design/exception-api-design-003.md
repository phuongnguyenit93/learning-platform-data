# Dùng loại ngoại lệ cụ thể thay vì `throws Exception` khi thiết kế API Java

> **Chủ đề:** Java Core → Exception → Thiết kế API. Mệnh đề `throws` là một phần của **hợp đồng phương thức** đối với checked exceptions. Khai báo `throws Exception` tuy hợp lệ nhưng thường **quá rộng** cho API ứng dụng/thư viện: người gọi không biết chính xác mình cần xử lý lỗi nào, khó phân nhánh chính sách khôi phục, và có thể vô tình phụ thuộc vào một hợp đồng cho phép quá nhiều loại thất bại. Hãy ưu tiên các loại ngoại lệ **có ngữ nghĩa, ở đúng mức trừu tượng và đủ hẹp**, chẳng hạn `IOException`, `ParseException` hoặc một custom checked exception phù hợp; đồng thời hiểu rằng không phải API nào cũng cần checked exception.

## 1. `throws Exception` có nghĩa là gì?

Một khai báo:

```java
public String load() throws Exception {
    // ...
}
```

nói với Java compiler rằng phương thức có thể kết thúc bất thường bằng một **checked exception** thuộc `Exception`, trong đó có `IOException`, `SQLException`, `ReflectiveOperationException`, custom checked exceptions và nhiều loại khác. Nó **không** khẳng định method luôn có lỗi, cũng không có nghĩa tất cả các subtype đều thực sự xuất hiện.

Hai ý cần tách riêng:

1. **Tập loại checked mà chữ ký cho phép:** `throws Exception` rộng hơn `throws IOException`.
2. **Những lỗi thực tế có thể xảy ra:** phụ thuộc vào mã chạy và các phương thức được gọi.

`Exception` còn là lớp cha của `RuntimeException`, nhưng các subclass unchecked như `IllegalArgumentException` **không cần** kê trong `throws` dù caller có thể gặp chúng.

### 1.1. Cây loại ngoại lệ liên quan

```text
Throwable
├── Error                         (unchecked)
└── Exception
    ├── IOException              (checked)
    │   └── FileNotFoundException (checked)
    ├── SQLException              (checked)
    ├── ParseException            (checked)
    ├── ReflectiveOperationException (checked)
    └── RuntimeException          (unchecked)
        ├── IllegalArgumentException
        └── IllegalStateException
```

Một `throws IOException` không bắt buộc kê mọi subtype `FileNotFoundException`: subtype đã nằm trong hợp đồng của superclass. Ngược lại, `throws FileNotFoundException` chỉ công bố nhánh hẹp và **không cho method tùy ý để `IOException` loại khác thoát theo checked contract**.

### 1.2. So sánh trực tiếp

```java
// Rộng nhưng hợp lệ về cú pháp:
static String readConfig() throws Exception {
    return java.nio.file.Files.readString(
            java.nio.file.Path.of("config.txt"));
}

// Rõ hơn khi thao tác chủ yếu liên quan I/O:
static String readConfigSpecific() throws java.io.IOException {
    return java.nio.file.Files.readString(
            java.nio.file.Path.of("config.txt"));
}
```

Đây là **hai method minh họa**, không phải một chương trình độc lập; cả hai có thể ném lỗi khi không đọc được file thật. Chữ ký thứ hai nói đúng nhóm failure được API trực tiếp sử dụng, giúp caller hiểu có thể chọn nguồn khác, báo lỗi đọc file hoặc dừng tác vụ.

**Không có quy tắc tuyệt đối** phải khai báo class con nhỏ nhất có thể tưởng tượng. Chọn loại **đủ cụ thể cho quyết định của caller** và đủ ổn định trước những thay đổi nội bộ.

## 2. Tại sao khai báo quá rộng làm caller khó xử lý?

Xét API:

```java
interface DocumentRepository {
    String load(String documentId) throws Exception;
}
```

Một caller không biết `load` có thể ném checked `IOException`, `SQLException`, `ParseException` hay loại khác. Code gọi phải xét toàn bộ `Exception`.

```java
try {
    String text = repository.load("DOC-1");
    System.out.println(text);
} catch (Exception e) {
    // Xử lý chung hoặc ném lên tiếp.
}
```

Đây là mảnh code cần biến `repository` đã khởi tạo. `catch(Exception)` có thể trở thành một nhánh quá rộng với nhiều failure **khác ý nghĩa**:

- File không tồn tại: có thể cho người dùng chọn file khác.
- Timeout từ dịch vụ phụ thuộc: có thể retry **nếu thao tác an toàn để retry**.
- Tài liệu không hợp lệ: cần thông báo dữ liệu sai, thường không retry.
- Bug lập trình như `NullPointerException`: không nên vô tình coi là lỗi tạm thời có thể retry.

**Một catch rộng không sai cú pháp**, nhưng nếu code “log rồi trả null” hoặc “retry mọi trường hợp”, nó có thể che bug và làm hợp đồng kết quả sai.

### 2.1. Compiler giúp được gì?

Với:

```java
void handle() throws Exception {
    repository.load("DOC-1");
}
```

compiler thấy method gọi đã được bao phủ, nhưng không giúp người bảo trì biết liệu cần xử lý lỗi file, database, parse hay nghiệp vụ.

Nếu chữ ký được làm cụ thể:

```java
interface DocumentRepository {
    String load(String documentId)
            throws java.io.IOException, DocumentFormatException;
}
```

caller nhìn vào API có thể quyết định **khôi phục I/O** khác với **từ chối format sai**. `DocumentFormatException` ở đây là một custom checked exception cần khai báo trong dự án (ví dụ sẽ có bên dưới).

### 2.2. Có thể vẫn viết `catch(IOException)` khi API `throws Exception`?

Có thể có những trường hợp `catch(IOException)` hợp lệ về compile-time vì API khai báo `throws Exception` — nhưng handler đó **không đủ** để xử lý toàn bộ checked `Exception` còn lại.

```java
try {
    broadApi(); // Khai báo throws Exception.
} catch (java.io.IOException e) {
    System.out.println("I/O");
} catch (Exception e) {
    System.out.println("Checked khác / unchecked khác");
}
```

Đây là mảnh code có `broadApi()` giả định. Handler `catch(Exception)` còn lại bắt cả những `RuntimeException` subtype, nên nếu code đó cố “phục hồi mọi lỗi” sẽ rất nguy hiểm. **Thu hẹp chữ ký ở API** có thể giảm nhu cầu về handler chung quá rộng ngay từ gốc.

## 3. Nguyên tắc chọn ngoại lệ có ý nghĩa

Một loại ngoại lệ tốt giúp caller trả lời:

1. **Điều gì thất bại?** Đọc file, phân tích cú pháp, kết nối, xác nhận trạng thái hay vi phạm hợp đồng?
2. **Ai có thể xử lý?** Caller trực tiếp, tầng service, retry layer, UI hay chỉ ranh giới log?
3. **Có thể làm gì?** Thử input khác, fallback, retry có điều kiện, hủy thao tác, báo lỗi người dùng?
4. **Có nên tiết lộ chi tiết bên trong?** Một service domain có cần public hóa `SQLException` không?
5. **Loại đó có ổn định khi implementation thay đổi?** Nếu đổi storage từ file sang HTTP, API có cần đổi `throws IOException`?

Các câu trả lời có thể dẫn tới:

- **Loại JDK phù hợp**, ví dụ `IOException` khi API bản chất là thao tác I/O.
- **Một custom checked exception**, ví dụ `DocumentFormatException extends Exception` cho dữ liệu được yêu cầu phải có định dạng hợp lệ.
- **Một custom unchecked exception**, ví dụ `InvalidTransitionException extends IllegalStateException` cho vi phạm trạng thái trong hợp đồng thao tác.
- **Result type**, ví dụ `ValidationResult` nếu nhiều vấn đề nhập liệu là kết quả dự kiến bình thường chứ không nên ném.
- **Không khai báo checked exception**, nếu method không có đường checked failure cần lộ ra.

**Độ cụ thể không có nghĩa tạo class mới cho từng dòng lỗi.** Loại ngoại lệ phải phản ánh một **phân loại xử lý hữu ích**, không chỉ một tên kỹ thuật.

## 4. `throws Exception` vs `throws IOException`

Giả sử một thư viện cung cấp hàm đọc text. Chữ ký:

```java
static String readText(Path path) throws IOException;
```

nói rõ failure liên quan I/O. Caller có thể bắt `IOException`, đọc cause/metadata, báo lỗi hoặc chuyển sang một nguồn dự phòng.

Còn:

```java
static String readText(Path path) throws Exception;
```

cho phép nhiều checked failures hơn. Lúc phát hành API, lựa chọn rộng có thể khiến người gọi phải xử lý `Exception` dù implementation chỉ đọc file. Khi lập trình lâu dài, một chữ ký rộng làm giảm giá trị tài liệu của API.

### 4.1. Java 17 — demo 1: phân biệt IOException và subtype

Tạo **`SpecificFileContractDemo.java`**:

```java
import java.io.FileNotFoundException;
import java.io.IOException;

public class SpecificFileContractDemo {
    static String read(String key) throws IOException {
        if ("missing".equals(key)) {
            throw new FileNotFoundException("Không thấy " + key);
        }
        if ("offline".equals(key)) {
            throw new IOException("Thiết bị không sẵn sàng");
        }
        return "data:" + key;
    }

    public static void main(String[] args) {
        for (String key : new String[] {
                "ok", "missing", "offline"
        }) {
            try {
                System.out.println("OK: " + read(key));
            } catch (FileNotFoundException e) {
                System.out.println("MISSING: "
                        + e.getClass().getSimpleName());
            } catch (IOException e) {
                System.out.println("IO: "
                        + e.getClass().getSimpleName());
            }
        }
    }
}
```

Biên dịch/chạy JDK 17+:

```bash
javac -encoding UTF-8 SpecificFileContractDemo.java
java SpecificFileContractDemo
```

Stdout:

```text
OK: data:ok
MISSING: FileNotFoundException
IO: IOException
```

Giải thích:

- `read` công bố **`throws IOException`**.
- Cả `FileNotFoundException` và `IOException` đều hợp lệ để thoát, vì loại thứ nhất là subtype của loại thứ hai.
- Caller **được phép** đặt catch chuyên biệt trước catch tổng quát.
- Đảo thứ tự (bắt `IOException` trước `FileNotFoundException`) gây lỗi unreachable handler.
- Bài cố tình tạo IOException có kiểm soát; không cần tạo file hay môi trường I/O thật để tái hiện.
- Không có lý do thêm `throws Exception` vào `read` chỉ vì method có thể thất bại.

### 4.2. Chọn loại cha đủ đúng mức

Không nhất thiết phải khai báo `throws FileNotFoundException` chỉ vì implementation hiện tại chỉ mở file. API thao tác I/O có thể hợp lý hơn khi công bố `IOException` vì tương lai có thể gặp những lỗi I/O khác cùng ý nghĩa. Đây là **hợp đồng ổn định hơn**, vẫn chính xác về nhóm failure.

Ngược lại, nếu API có ý nghĩa “tra một tên file, chỉ công bố tình huống không tìm thấy” và đảm bảo bắt/translate các I/O failure khác, `FileNotFoundException` hoặc một loại domain riêng có thể hợp lý. Quy tắc là **đúng theo hành vi được cam kết**, không máy móc chọn subtype sâu nhất.

## 5. Hai loại checked failure độc lập: kê rõ cả hai

Một method có thể gặp **hai nhóm lỗi thật sự khác nhau** và caller cần phân biệt. Khi đó thay vì `throws Exception`, khai báo nhiều loại cụ thể:

```java
String importDocument(String raw)
        throws IOException, DocumentFormatException;
```

Đây là method signature minh họa. Lỗi I/O có thể tạm thời; lỗi định dạng dữ liệu thường đòi sửa input. Chúng không có quan hệ subtype với nhau.

### 5.1. Java 17 — demo 2: I/O và dữ liệu sai hợp đồng

Tạo **`TwoSpecificFailuresDemo.java`**:

```java
import java.io.IOException;

public class TwoSpecificFailuresDemo {
    static final class InvalidRecordException extends Exception {
        InvalidRecordException(String message) {
            super(message);
        }
    }

    static String load(String raw)
            throws IOException, InvalidRecordException {
        if ("offline".equals(raw)) {
            throw new IOException("Kho không truy cập");
        }
        if (!raw.startsWith("ID:")) {
            throw new InvalidRecordException("Sai định dạng");
        }
        return raw.substring(3);
    }

    public static void main(String[] args) {
        for (String value : new String[] {
                "ID:42", "oops", "offline"
        }) {
            try {
                System.out.println("OK: " + load(value));
            } catch (InvalidRecordException e) {
                System.out.println("FORMAT: " + e.getMessage());
            } catch (IOException e) {
                System.out.println("IO: " + e.getMessage());
            }
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 TwoSpecificFailuresDemo.java
java TwoSpecificFailuresDemo
```

Stdout:

```text
OK: 42
FORMAT: Sai định dạng
IO: Kho không truy cập
```

**Lý do thiết kế hợp lý:**

1. `InvalidRecordException` là **checked custom exception**, giúp caller có nhánh xử lý riêng cho dữ liệu sai.
2. `IOException` thể hiện lỗi truy cập dữ liệu, không bị gộp với lỗi format.
3. Method `load` không khai báo `throws Exception`.
4. Caller được chọn riêng cách phản ứng cho mỗi nhóm lỗi.
5. Nếu dữ liệu sai định dạng là phản hồi rất thường gặp, có thể cân nhắc kiểu kết quả có cấu trúc thay cho checked exception; thiết kế ở ví dụ chỉ nhằm thể hiện hợp đồng `throws`.
6. Khi `raw == null`, mã hiện tại sẽ gây `NullPointerException` do gọi `startsWith`. API thật cần kiểm tra `null`/input invariants và mô tả chúng; demo dùng chuỗi không null để tập trung vào checked exceptions.

### 5.2. Multi-catch khi chính sách xử lý trùng nhau

Nếu caller thật sự muốn xử lý cùng cách cho cả hai checked exception:

```java
try {
    importData();
} catch (IOException | InvalidRecordException e) {
    reportFailure(e);
}
```

Đây là mảnh code minh họa, cần định nghĩa `importData`, `reportFailure` và `InvalidRecordException` trong dự án. Multi-catch dùng được khi hai loại exception **không thuộc quan hệ cha–con**. Không được viết `catch(IOException | FileNotFoundException e)`, vì `FileNotFoundException` là subtype của `IOException`.

Ngay cả khi xử lý chung, **chữ ký cụ thể vẫn có ích**: người dùng API biết chính xác những failure có thể xảy ra, và có thể chọn handler riêng sau này.

## 6. Khi không nên tiết lộ loại exception hạ tầng

Một API domain có thể dùng JDBC ở bên dưới:

```java
// Hợp đồng gắn chặt tầng domain vào implementation JDBC:
Order loadOrder(String id) throws SQLException;
```

Nếu service đổi từ JDBC sang REST hoặc nguồn khác, liệu caller có nên cần sửa code dù hợp đồng nghiệp vụ “lấy đơn hàng” không thay đổi? Đó là dấu hiệu API có thể đang **rò rỉ abstraction của tầng dưới**.

Một lựa chọn:

```java
Order loadOrder(String id) throws OrderRepositoryException;
```

`OrderRepositoryException` là custom checked exception có ý nghĩa “tầng lưu trữ đơn hàng thất bại”. Tầng repository/service **bắt `SQLException`, truyền cause vào custom exception** và chỉ công bố hợp đồng có ngữ nghĩa ổn định cho domain.

### 6.1. Java 17 — demo 3: dịch SQLException sang exception domain

Tạo **`ExceptionTranslationDemo.java`**:

```java
import java.sql.SQLException;

public class ExceptionTranslationDemo {
    static final class CatalogUnavailableException
            extends Exception {
        CatalogUnavailableException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static String readFromDatabase() throws SQLException {
        throw new SQLException("Database down", "08001");
    }

    static String loadCatalog()
            throws CatalogUnavailableException {
        try {
            return readFromDatabase();
        } catch (SQLException e) {
            throw new CatalogUnavailableException(
                    "Không tải được catalog", e);
        }
    }

    public static void main(String[] args) {
        try {
            System.out.println(loadCatalog());
        } catch (CatalogUnavailableException e) {
            System.out.println("Boundary: "
                    + e.getClass().getSimpleName());
            System.out.println("Cause: "
                    + e.getCause().getClass().getSimpleName());
            SQLException sql = (SQLException) e.getCause();
            System.out.println("SQLState: " + sql.getSQLState());
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 ExceptionTranslationDemo.java
java ExceptionTranslationDemo
```

Stdout:

```text
Boundary: CatalogUnavailableException
Cause: SQLException
SQLState: 08001
```

**Ý nghĩa:**

- `readFromDatabase()` vẫn có hợp đồng `throws SQLException`, đúng mức hạ tầng.
- `loadCatalog()` chuyển đổi lỗi tại **ranh giới abstraction** và công bố `CatalogUnavailableException`.
- Constructor `super(message, cause)` giữ `SQLException` thật làm cause; không ném một exception chỉ chứa `e.getMessage()` rồi mất đường nguyên nhân.
- Caller service chỉ cần biết failure catalog, không buộc phải phụ thuộc trực tiếp package JDBC trong chữ ký.
- Demo cast `SQLException` ở `main` để chứng minh cause; một caller tổng quát **không nên** cast mọi `getCause()` thành `SQLException` nếu implementation có thể thay đổi. Hãy phân loại bằng `instanceof` hoặc chính sách chẩn đoán thích hợp.

### 6.2. Dịch exception không phải giấu lỗi

Một số anti-pattern:

```java
try {
    saveToDatabase();
} catch (SQLException ignored) {
    return true; // CỐ Ý SAI: giả thành công khi thao tác thất bại.
}
```

Đây là mảnh code minh họa chưa có `saveToDatabase`. Nếu không có fallback/compensation đã được thiết kế, **đừng nuốt lỗi**. Dịch lỗi phải giữ trạng thái thất bại và phục vụ abstraction, không biến lỗi thành success.

## 7. Checked vs unchecked: không phải cứ “cụ thể” là checked

Một public method không cần `throws` cho mọi tình huống lỗi:

```java
static void setDiscount(int percent) {
    if (percent < 0 || percent > 100) {
        throw new IllegalArgumentException(
                "percent phải thuộc [0,100]");
    }
}
```

`IllegalArgumentException` là loại **cụ thể và unchecked**, phù hợp khi caller vi phạm tiền điều kiện. Compiler không yêu cầu kê `throws IllegalArgumentException`, dù Java cho phép liệt kê nếu muốn tài liệu hóa.

**Hai quyết định riêng biệt:**

1. Lỗi là một điều kiện có thể xảy ra trong luồng nghiệp vụ mà caller nên được compiler nhắc xử lý, hay là vi phạm contract/lỗi runtime?
2. Loại exception được chọn có cụ thể và có ý nghĩa với caller không?

Đừng biến mọi `IOException` thành unchecked chỉ để xóa `throws`, cũng đừng tạo checked exception cho mọi phép validation.

### 7.1. Java 17 — demo 4: cả checked và unchecked trong một API

Tạo **`CheckedUncheckedContractDemo.java`**:

```java
import java.io.IOException;

public class CheckedUncheckedContractDemo {
    static int compute(int input) throws IOException {
        if (input < 0) {
            throw new IllegalArgumentException("input âm");
        }
        if (input == 0) {
            throw new IOException("Nguồn dữ liệu rỗng");
        }
        return input * 2;
    }

    public static void main(String[] args) {
        for (int input : new int[] {3, -1, 0}) {
            try {
                System.out.println("OK: " + compute(input));
            } catch (IllegalArgumentException e) {
                System.out.println("INVALID: "
                        + e.getClass().getSimpleName());
            } catch (IOException e) {
                System.out.println("IO: "
                        + e.getClass().getSimpleName());
            }
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 CheckedUncheckedContractDemo.java
java CheckedUncheckedContractDemo
```

Stdout:

```text
OK: 6
INVALID: IllegalArgumentException
IO: IOException
```

Giải thích:

- `compute` công bố `IOException` vì đó là một checked failure.
- `IllegalArgumentException` vẫn có thể xảy ra nhưng không cần kê trong `throws`.
- Caller có thể bắt unchecked exception nếu có chính sách phản hồi input đúng; không cần làm vậy trong mọi đoạn code.
- `int * 2` trong demo có thể tràn số với input cực lớn; bài chọn input nhỏ. API production phải xem điều kiện số học riêng (`Math.multiplyExact` nếu cần).
- Đừng hiểu `throws IOException` nghĩa là “chỉ có IOException, không có RuntimeException”.

## 8. Lợi ích khi caller có thể viết handler theo từng loại

Khi API cụ thể, caller dễ thể hiện **chính sách khác nhau**:

| Loại failure | Hành động có thể phù hợp | Không nên mặc định |
| --- | --- | --- |
| `FileNotFoundException` | Chọn đường dẫn khác hoặc báo thiếu file | Retry vô hạn cùng path |
| `IOException` tạm thời | Retry có giới hạn nếu thao tác idempotent | Retry mọi I/O failure |
| `InvalidRecordException` | Yêu cầu sửa input | Retry I/O và hy vọng dữ liệu đúng |
| `SQLException` ở tầng JDBC | Quản lý transaction, đọc SQL state nếu cần | Phơi SQL internals cho API public |
| `CatalogUnavailableException` | Báo dịch vụ phụ thuộc không sẵn sàng | Cast mọi cause sang SQLException |
| `IllegalArgumentException` | Sửa tham số do caller cung cấp | Bắt rồi che bug và trả success |
| `IllegalStateException` | Sửa trạng thái/sequence thao tác | Tự giả định retry sẽ sửa invariant |
| `InterruptedException` | Tôn trọng interruption policy | Nuốt interrupt mà không khôi phục |

**Một loại exception không quyết định tự động chính sách retry.** Ví dụ `IOException` có thể bao gồm lỗi permission, file không tồn tại hoặc kết nối tạm mất. Cần metadata ngữ nghĩa, tính idempotent, trạng thái side effect và yêu cầu nghiệp vụ.

## 9. Viết `catch` cụ thể và sắp xếp đúng thứ tự

Trong Java, handler được xét từ trên xuống; lớp con phải ở trước lớp cha nếu cần phân biệt.

```java
try {
    readFile();
} catch (FileNotFoundException e) {
    handleMissingFile(e);
} catch (IOException e) {
    handleOtherIo(e);
}
```

Đây là mảnh code với ba hàm giả định. Nếu đặt `catch(IOException)` trước `catch(FileNotFoundException)`, handler sau không thể tới được.

### 9.1. `catch(Exception)` chỉ tại ranh giới thực sự cần?

Một ranh giới như CLI dispatcher, task runner, executor hoặc server request boundary có thể bắt rộng để **ghi log, chuyển lỗi thành phản hồi thất bại an toàn và không phá hủy việc điều phối khác**, sau khi các tầng gần nguồn đã thực hiện xử lý cụ thể.

Nhưng:

- `catch(Exception)` còn nhận cả `RuntimeException`; không coi mọi bug là một lỗi dự kiến có thể phục hồi.
- Nó **không** bắt `Error`. Catch `Throwable` còn rộng hơn, cần chính sách cực kỳ thận trọng.
- Bắt rộng ở boundary **không biện minh** cho việc mọi method ở mọi tầng đều khai báo `throws Exception`.
- Nếu tầng đó không thể giải quyết lỗi, có thể ném tiếp hoặc chuyển sang lỗi phù hợp, giữ cause.
- Không báo “thành công” chỉ vì exception đã bị bắt.

## 10. Java 17 — demo 5: multi-catch cho lỗi checked độc lập

Tạo **`MultiCatchContractDemo.java`**:

```java
import java.io.IOException;
import java.text.ParseException;

public class MultiCatchContractDemo {
    enum Mode { OK, IO, PARSE }

    static String run(Mode mode)
            throws IOException, ParseException {
        return switch (mode) {
            case OK -> "success";
            case IO -> throw new IOException("Lỗi thiết bị");
            case PARSE -> throw new ParseException("Sai ngày", 0);
        };
    }

    public static void main(String[] args) {
        for (Mode mode : Mode.values()) {
            try {
                System.out.println("OK: " + run(mode));
            } catch (IOException | ParseException e) {
                System.out.println("FAILED: "
                        + e.getClass().getSimpleName());
            }
        }
    }
}
```

Chạy JDK 17+:

```bash
javac -encoding UTF-8 MultiCatchContractDemo.java
java MultiCatchContractDemo
```

Stdout:

```text
OK: success
FAILED: IOException
FAILED: ParseException
```

Vì sao hợp lệ?

- `IOException` và `ParseException` đều là checked exceptions nhưng **không có quan hệ cha–con**.
- `run` công bố rõ hai loại.
- Một multi-catch cho cả hai nếu caller chọn chính sách giống nhau.
- Nếu handler cần xử lý khác, tách thành hai `catch`.
- `switch` expression với nhánh `throw` là tính năng ổn định trong Java 17.
- Trong multi-catch, biến `e` có kiểu được tính theo luật chung và là effectively final; không viết code giả định lúc nào `e` cũng là `IOException`.

### 10.1. Sai: multi-catch cha và con

```java
// CỐ Ý KHÔNG BIÊN DỊCH:
catch (IOException | FileNotFoundException e) {
    // Hai lựa chọn có quan hệ kế thừa.
}
```

Chọn `catch(IOException e)` nếu cần xử lý chung, hoặc hai handler theo thứ tự subtype rồi superclass.

## 11. Interface và override: `throws` là hợp đồng thay thế được

Một implementation của interface không được **mở rộng** danh sách checked exceptions so với phương thức interface bị override.

```java
interface Loader {
    String load() throws IOException;
}
```

Hợp lệ:

```java
final class FileLoader implements Loader {
    @Override
    public String load() throws FileNotFoundException {
        throw new FileNotFoundException("missing");
    }
}
```

Không hợp lệ:

```java
// CỐ Ý KHÔNG BIÊN DỊCH:
final class BroadLoader implements Loader {
    @Override
    public String load() throws Exception {
        return "x";
    }
}
```

`Exception` rộng hơn `IOException` nên caller của `Loader` không được hứa xử lý tất cả checked subtypes của Exception. Implementation phải tôn trọng contract: cùng loại checked, subtype phù hợp, hoặc ít checked hơn.

### 11.1. Java 17 — demo 6: interface và reference type

Tạo **`OverrideSpecificThrowsDemo.java`**:

```java
import java.io.FileNotFoundException;
import java.io.IOException;

public class OverrideSpecificThrowsDemo {
    interface Reader {
        String read() throws IOException;
    }

    static final class FileReader implements Reader {
        @Override
        public String read() throws FileNotFoundException {
            throw new FileNotFoundException("missing");
        }
    }

    public static void main(String[] args) {
        FileReader concrete = new FileReader();
        try {
            concrete.read();
        } catch (FileNotFoundException e) {
            System.out.println("Concrete catches: "
                    + e.getClass().getSimpleName());
        }

        Reader api = concrete;
        try {
            api.read();
        } catch (IOException e) {
            System.out.println("Interface catches: "
                    + e.getClass().getSimpleName());
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 OverrideSpecificThrowsDemo.java
java OverrideSpecificThrowsDemo
```

Stdout:

```text
Concrete catches: FileNotFoundException
Interface catches: FileNotFoundException
```

**Phân biệt hai thứ:**

1. **Nghĩa vụ compiler** ở caller phụ thuộc method được xác định từ **kiểu tham chiếu tĩnh**. `FileReader.read` công bố `FileNotFoundException`; `Reader.read` công bố `IOException`.
2. **Đối tượng exception runtime** là `FileNotFoundException` trong cả hai lần gọi; upcast receiver thành `Reader` không thay object error thành `IOException`.

Nếu không có lý do hợp đồng, implementation không nên tự thêm `throws Exception` để “dự phòng lỗi sau này” vì như vậy vi phạm interface.

## 12. Nhiều interface có `throws` khác nhau

Một class có thể implement hai interface có cùng method signature, nhưng mỗi interface kê checked exception khác. Implementation phải thỏa **đồng thời** các quy tắc override.

Ví dụ:

```java
interface A {
    void execute() throws IOException;
}
interface B {
    void execute() throws SQLException;
}

final class Combined implements A, B {
    @Override
    public void execute() {
        System.out.println("done");
    }
}
```

Đây là mảnh code minh họa cần import `IOException`/`SQLException`. Vì hai loại checked không liên quan, `Combined.execute()` **không được** khai báo `throws IOException, SQLException`; bỏ checked throws làm nó hợp lệ với cả hai.

Hãy nhớ: `throws Exception` càng không phải cách khắc phục khi hợp đồng interface **hẹp hơn**. Chữ ký implementation không thể mở rộng hợp đồng tùy ý.

## 13. Khi thay đổi `throws`, kiểm tra tương thích mã nguồn

Khai báo `throws` là một phần của hợp đồng kiểm tra checked exceptions. Nếu public API trước đây chỉ có `throws ParseException` rồi thêm `IOException`, một caller chỉ bắt `ParseException` có thể **không biên dịch lại được**:

~~~java
// Hai phiên bản chữ ký minh họa, không cùng khai báo trong một lớp.
String parse(String input) throws ParseException;
// Phiên bản kế tiếp:
String parse(String input) throws ParseException, IOException;
~~~

Thu hẹp hoặc bỏ checked `throws` cũng có thể làm handler checked ở caller trở nên không thể tới được sau khi biên dịch lại. Tuy nhiên chỉ đổi mệnh đề `throws` **không tự làm thay đổi method descriptor ở JVM**; cần tách *source*, *binary* và *behavioral compatibility*. Không nên thay public `throws` trong một thư viện chỉ vì implementation hiện tại không còn ném một lỗi; hãy kiểm tra caller, override và lộ trình chuyển đổi. Bài về **tác động tương thích khi thay đổi hợp đồng ngoại lệ** phân tích ma trận và các chiến lược nâng cấp đầy đủ.

## 14. Dùng Javadoc `@throws` để giải thích điều kiện, không chỉ liệt kê kiểu

Mệnh đề `throws` thông báo checked exception cho compiler; `@throws` trong Javadoc cho caller biết **khi nào** exception phát sinh. Trong tài liệu cho phương thức `load(String documentId) throws IOException`, có thể nêu: `@throws IOException nếu nguồn dữ liệu không đọc được` và `@throws IllegalArgumentException nếu documentId rỗng`. Đây là nội dung minh họa Javadoc, không phải khai báo phương thức mới.

Có thể tài liệu hóa cả **unchecked exception** bằng `@throws` dù không cần khai báo nó trong chữ ký. Tránh mô tả mơ hồ kiểu “nếu xảy ra lỗi”; viết điều kiện cụ thể, cập nhật Javadoc cùng test hợp đồng. Quy tắc sinh tài liệu, thẻ inline, override và nhiều nhánh thất bại được học đầy đủ ở bài **tài liệu hóa bằng `@throws`**.

## 15. `throws` ở constructor, resource và API I/O

Quy tắc “cụ thể” áp dụng cả cho constructor và resource cleanup.

```java
public FileStore(Path root) throws IOException {
    // Đọc hoặc tạo dữ liệu trên file system.
}
```

Nếu constructor có thể ném checked `IOException`, caller cần xử lý/khai báo. Không có lý do khai `throws Exception` khi chỉ có I/O như một loại checked thật sự.

Khi dùng `try-with-resources`, cả thân `try` và phương thức `close()` của resource có thể ném checked exceptions. Nếu kiểu resource công bố `close() throws IOException`, API bọc ngoài có thể dùng `throws IOException`; nhưng nếu resource được khai báo kiểu `AutoCloseable` chung với `close() throws Exception`, compiler có thể phải xét `Exception` ở điểm close. **Kiểu tĩnh của resource** và API `close` ảnh hưởng hợp đồng.

### 15.1. Java 17 — demo 7: `Closeable` cho checked IOException cụ thể

Tạo **`CloseableSpecificThrowsDemo.java`**:

```java
import java.io.Closeable;
import java.io.IOException;

public class CloseableSpecificThrowsDemo {
    static final class Resource implements Closeable {
        String read() throws IOException {
            return "ok";
        }

        @Override
        public void close() throws IOException {
            System.out.println("closing");
        }
    }

    static String load() throws IOException {
        try (Resource resource = new Resource()) {
            return resource.read();
        }
    }

    public static void main(String[] args) {
        try {
            String result = load();
            System.out.println("result: " + result);
        } catch (IOException e) {
            System.out.println("IO: " + e.getMessage());
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 CloseableSpecificThrowsDemo.java
java CloseableSpecificThrowsDemo
```

Stdout:

```text
closing
result: ok
```

Vì sao `load() throws IOException` là đủ?

- `Resource.read` và `Closeable.close` đều có `throws IOException`.
- Try-with-resources bảo đảm `close` được gọi khi rời `try` trong các đường thực thi phù hợp.
- Không cần `throws Exception` khi các nguồn checked failure của ví dụ đều là I/O.
- Nếu `read` và `close` cùng ném lỗi, Java có cơ chế primary/suppressed exceptions; chúng không tự biến thành `Exception` rộng chỉ vì có nhiều Throwable.
- `try-with-resources` không bảo đảm thao tác đọc thành công hoặc side effect được rollback; nó quản lý việc đóng resource.

### 15.2. Vì sao khai resource là `AutoCloseable` có thể làm `throws` rộng?

`AutoCloseable.close()` công bố `throws Exception`. Nếu code chỉ thấy kiểu `AutoCloseable` và không bắt/translate lỗi khi đóng, nó phải tính cả checked `Exception` từ `close`.

Giải pháp không phải tự ép cast tùy tiện, mà là chọn interface resource có hợp đồng hẹp phù hợp (`Closeable` cho I/O) hoặc xử lý/dịch lỗi ở ranh giới có ý nghĩa.

## 16. Exception chaining: giữ `cause` khi chọn exception cụ thể

Chuyển `SQLException` thành `CatalogUnavailableException` có ích chỉ khi không làm mất nguyên nhân gốc.

Nên:

```java
throw new CatalogUnavailableException(
        "Không tải được catalog", sqlException);
```

Không nên:

```java
throw new CatalogUnavailableException(
        sqlException.getMessage(), null);
```

Các mảnh code giả định constructor phù hợp và biến `sqlException`. Cách thứ hai bỏ cause, làm khó xem stack gốc, vendor code/SQL state và chuỗi lỗi.

**Message và cause có mục đích khác nhau:**

- Message: mô tả cho người đọc theo tầng hiện tại.
- Cause: liên kết đến failure tầng dưới.
- Custom typed context: các ID/code an toàn, nếu caller cần xử lý có cấu trúc.
- Suppressed: các lỗi phụ bị giữ lại trong cùng tình huống, đặc biệt khi đóng resource thất bại.

Không copy thủ công toàn bộ stack trace hoặc tạo một field `originalException` trùng với `getCause()` nếu không có nhu cầu riêng.

## 17. Khi nào nên bọc checked thành unchecked?

Một thư viện callback như `Function.apply` không công bố checked exception. Có trường hợp cần bọc `IOException` thành `UncheckedIOException` và giữ cause:

```java
Function<Path, String> read = path -> {
    try {
        return Files.readString(path);
    } catch (IOException e) {
        throw new UncheckedIOException("Không đọc được", e);
    }
};
```

Đây là **mảnh code** cần import `Function`/`Path`/`Files`/`IOException`/`UncheckedIOException`. Nó đổi **hình thức báo lỗi** qua API callback, không biến I/O failure thành success.

Nhưng không nên xem đây là lời khuyên tổng quát xóa checked `throws` khỏi mọi API. Nếu bạn kiểm soát method khai báo, một `throws IOException` rõ ràng có thể phù hợp hơn việc ép lỗi đi qua unchecked wrapper.

### 17.1. `InterruptedException` cần chính sách riêng

Nếu code bắt `InterruptedException` rồi dịch lỗi, phải cân nhắc bảo toàn tín hiệu interruption: có thể ném tiếp `InterruptedException` khi API cho phép, hoặc khôi phục interrupt flag bằng `Thread.currentThread().interrupt()` trước khi chuyển sang một exception khác, tùy hợp đồng.

Đừng chỉ `catch(Exception ignored)` quanh thao tác blocking rồi nuốt luôn interruption. Đây là ví dụ mạnh cho thấy `throws Exception` làm nhiều failure với chính sách khác nhau bị gộp thiếu rõ ràng.

## 18. `throws Exception` có luôn là lỗi thiết kế không?

**Không.** Nó có thể hợp lý ở một số **ranh giới tổng quát**:

- `public static void main(String[] args) throws Exception` trong **chương trình minh họa nhỏ**, khi mục tiêu chỉ là học một API khác và chấp nhận để chương trình kết thúc khi có lỗi.
- Test harness hoặc runner nội bộ, nơi callback được định nghĩa để cho phép nhiều checked exception.
- `java.util.concurrent.Callable<V>.call() throws Exception`: một API chuẩn có hợp đồng tổng quát cố ý cho phép tác vụ báo checked failure.
- Framework/plugin abstraction chạy mã do ứng dụng khác cung cấp, khi tập loại checked chưa biết trước và caller được thiết kế như một dispatcher chung.
- Một boundary nhất định cần propagate mọi checked exception nhưng không hứa được một abstraction cụ thể hơn (cần tài liệu rõ và giới hạn phạm vi).

Vẫn cần xem liệu `throws Exception` có gây bất tiện cho **public API lâu dài** hay không. Đừng sử dụng nó ở mọi tầng chỉ vì dễ viết.

### 18.1. `main throws Exception` có khác library API?

Có về mục đích. `main` là entry point được JVM gọi; với một demo nhỏ, khai báo `throws Exception` đôi khi chấp nhận được vì không có caller Java khác phải triển khai policy. Một phương thức **public library** `load() throws Exception` có thể bị hàng trăm caller dùng trong nhiều năm; hợp đồng quá rộng trở thành chi phí bảo trì.

Trong tài liệu học Java, nên ưu tiên ví dụ có handler cụ thể để thể hiện behavior, nhưng không cần “cấm” tuyệt đối `main throws Exception`.

### 18.2. `Callable.call() throws Exception` là ví dụ có chủ đích

`Callable<V>` cho phép nhiều loại checked failure vì một task framework có thể chạy logic tùy ý. Tuy nhiên khi gửi task vào `ExecutorService` và gọi `Future.get()`, caller nhìn thấy **`ExecutionException`** (có cause là lỗi task) theo API Future, không nhất thiết nhận checked exception của task trực tiếp. Mỗi tầng vẫn cần hợp đồng riêng.

**Bài học:** “cụ thể” là theo tầng abstraction và vai trò caller, không có nghĩa mọi API generics đều phải biết mọi loại failure của tác vụ từ trước.

## 19. Generic `throws E`: giữ tính cụ thể cho callback do bạn kiểm soát

Khi thiết kế API nhận lambda có thể ném checked exception, thay vì bắt caller chịu `throws Exception` ở mọi nơi, có thể sử dụng type parameter.

```java
@FunctionalInterface
interface CheckedSupplier<T, E extends Exception> {
    T get() throws E;
}

static <T, E extends Exception> T execute(
        CheckedSupplier<T, E> action) throws E {
    return action.get();
}
```

Đây là các khai báo minh họa, không phải một chương trình standalone. Với callback có checked `IOException`, `E` có thể là `IOException`, nên method gọi `execute` không phải công bố `Exception` rộng chỉ vì API generic.

### 19.1. Java 17 — demo 8: truyền checked type qua generic

Tạo **`GenericSpecificThrowsDemo.java`**:

```java
import java.io.IOException;

public class GenericSpecificThrowsDemo {
    @FunctionalInterface
    interface CheckedSupplier<T, E extends Exception> {
        T get() throws E;
    }

    static <T, E extends Exception> T execute(
            CheckedSupplier<T, E> action) throws E {
        return action.get();
    }

    public static void main(String[] args) {
        try {
            String ok =
                    GenericSpecificThrowsDemo
                        .<String, IOException>execute(() -> "done");
            System.out.println("Value: " + ok);

            GenericSpecificThrowsDemo
                .<String, IOException>execute(() -> {
                    throw new IOException("lost");
                });
        } catch (IOException e) {
            System.out.println("I/O: " + e.getMessage());
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 GenericSpecificThrowsDemo.java
java GenericSpecificThrowsDemo
```

Stdout:

```text
Value: done
I/O: lost
```

Giải thích:

- `CheckedSupplier.get()` công bố checked `E`.
- `execute()` công bố `throws E` thay vì hard-code `throws Exception`.
- Ở call site, ví dụ khai báo tường minh `E = IOException` để tránh phụ thuộc vào chi tiết suy luận kiểu khi học.
- Lambda có thể ném `IOException` vì target functional interface **cho phép** checked exception đó.
- `Supplier<T>` chuẩn trong `java.util.function` lại **không** có `throws E`; không thể thay thế nó bằng custom `CheckedSupplier` một cách tự động trong API vốn nhận `Supplier`.
- Generic `E` đại diện cho một kiểu ngoại lệ, không phải một phép union tổng quát của các kiểu checked không liên quan.

## 20. Nhiều checked exception và API framework

Một framework nhận mã plugin có thể dùng interface:

```java
interface PluginAction {
    void execute() throws Exception;
}
```

Điều này có thể hợp lý vì plugin có thể làm I/O, SQL, parse và nhiều việc khác mà framework không biết trước. Tuy nhiên tại **biên gọi plugin**, framework nên:

- Xác định failure policy: log, đánh dấu task thất bại, cleanup.
- Không coi mọi `Exception` là transient hay retryable.
- Phân biệt hỏng plugin với vi phạm môi trường/permission, khi cần.
- Không bắt `Error` rồi trả thành công.
- Giữ cause khi chuyển lỗi sang `PluginExecutionException` hoặc result có cấu trúc.
- Không truyền thẳng stack trace nội bộ cho end user.
- Nếu các plugin có contract domain chung rõ ràng, có thể chọn một checked `PluginException` hẹp hơn `Exception`.

**Một exception riêng tên `PluginException` cũng có thể quá rộng** nếu nó gộp tất cả failure mà caller cần phân biệt. Chọn cấu trúc exception taxonomy dựa vào use cases thực tế, không theo số tầng lớp lớn nhất.

## 21. Nếu thất bại là kết cục nghiệp vụ dự kiến, cân nhắc kiểu kết quả

Không phải mọi đầu vào sai trong một luồng validation đều cần `throws`. Nếu caller muốn nhận nhiều lỗi trong một lần, một result có kiểu và mã lỗi có thể phù hợp:

~~~java
record FieldIssue(String field, String code) {}
record ValidationResult(java.util.List<FieldIssue> issues) {}
~~~

Đây là các record minh họa (Java 17), không phải toàn bộ chương trình. **Ngoại lệ cụ thể** vẫn đúng khi thao tác thất bại bất thường như không đọc được nguồn I/O; `Optional<T>` phù hợp hơn nếu việc **không có kết quả** là bình thường và không cần biết lý do. Bài “Chọn ngoại lệ, Optional hay kiểu kết quả có cấu trúc” là nơi so sánh và kiểm thử chi tiết ba lựa chọn.

## 22. Hạn chế tạo hierarchy custom quá sâu

Cụ thể không đồng nghĩa với hàng chục lớp:

```text
Exception
└── ApplicationException
    └── ServiceException
        └── DataException
            └── RepositoryException
                └── CatalogException
                    └── CatalogTimeoutException
```

Cây minh họa như trên có thể mang chi phí:

- Caller phải hiểu nhiều loại mà không có chính sách xử lý khác nhau thật.
- Tầng ứng dụng cần chuyển đổi qua nhiều wrapper, tạo stack/cause chain dài.
- Một hierarchy quá sâu làm API gắn với cách tổ chức package/tầng hiện tại.
- Nếu nhiều loại chỉ khác message, có thể một class với mã lỗi typed là đủ.
- Nếu quá ít loại, caller không thể phân biệt failure có ý nghĩa.

Một thiết kế vừa phải thường phân loại theo **khả năng phục hồi hoặc trách nhiệm xử lý**:

```text
CatalogException (checked)
├── CatalogNotFoundException
└── CatalogUnavailableException
```

Đây là ví dụ taxonomy, không yêu cầu mọi ứng dụng phải định nghĩa y hệt. Nếu `NotFound` là kết quả bình thường, có thể trả `Optional<Catalog>` hoặc result type thay cho exception.

## 23. Ngoại lệ cụ thể và dữ liệu ngữ cảnh có kiểu

Một loại exception rõ ràng có thể đi kèm getter có kiểu:

```java
final class ResourceNotFoundException extends Exception {
    private final String resourceId;

    ResourceNotFoundException(String resourceId) {
        super("Không tìm thấy tài nguyên");
        this.resourceId = java.util.Objects.requireNonNull(
                resourceId, "resourceId");
    }

    String resourceId() {
        return resourceId;
    }
}
```

Đây là class minh họa, không có `main`. Caller có thể biết **loại lỗi** và **ID nào liên quan**, không parse `getMessage()`.

Khi thiết kế:

- Chỉ giữ context cần cho hợp đồng xử lý/chẩn đoán.
- Không lưu password/token/raw request body trong exception.
- Không copy cause vào một field riêng nếu `Throwable.getCause()` đã đáp ứng.
- Không trùng `errorCode` và subtype có thể mâu thuẫn; nếu cả hai phục vụ API/telemetry, bảo đảm đồng bộ bằng thiết kế.
- Giữ context ổn định, tránh object graph mutable lớn.

**Thông điệp lỗi phục vụ con người; loại exception và getter typed phục vụ logic máy.**

## 24. Trường hợp checked exception được thư viện bọc bởi API khác

Một API có thể nhận callback nhưng không khai báo checked exception, chẳng hạn `Function.apply`/`Supplier.get`. Lúc đó bạn **không thể đơn giản thêm `throws IOException` vào lambda** nếu target functional method không có `throws`.

Các lựa chọn:

1. Xử lý checked exception trong lambda khi có fallback hợp nghĩa.
2. Bọc thành unchecked có cause, như `UncheckedIOException`.
3. Tự thiết kế functional interface có `throws E` nếu bạn kiểm soát API nhận callback.
4. Dùng vòng lặp hoặc method thường để giữ checked contract trực tiếp.

Khi API của framework chuyển lỗi qua `InvocationTargetException`, `ExecutionException` hoặc `CompletionException`, caller phải tuân theo **hợp đồng của tầng gọi** và tìm cause gốc theo cơ chế tương ứng. Không có một mệnh đề `throws IOException` của method nằm sâu nào tự xuất hiện ở mọi tầng.

**Điều này củng cố nguyên tắc:** chọn loại ngoại lệ đủ cụ thể nhưng **đúng abstraction boundary** mà caller đang sử dụng.

## 25. Thiết kế chính sách retry dựa vào semantics, không chỉ tên loại

Một `IOException` có thể bắt nguồn từ:

- file không tồn tại (retry y hệt thường vô ích);
- permission denied (cần quyền hoặc cấu hình);
- kết nối tạm thời mất (có thể retry có giới hạn);
- lỗi ghi giữa chừng (cần xem dữ liệu đã ghi đến đâu).

Vì vậy dù API có `throws IOException` cụ thể, caller **không tự được phép retry mọi IOException**. Tầng domain có thể cần thông tin riêng như error code, loại thao tác, timeout category, và idempotency.

Ngược lại, `throws Exception` lại làm retry policy khó đặt đúng vì quá nhiều loại failure không liên quan có thể đi qua một handler chung.

### 25.1. Ví dụ quyết định chính sách

| Tình huống | Lựa chọn hướng xử lý |
| --- | --- |
| Thiếu file nhập | Yêu cầu đường dẫn hợp lệ hoặc chọn file |
| File hiện có bị lỗi format | Báo giá trị/field sai, không retry tự động |
| Kết nối bất ổn | Retry giới hạn nếu thao tác cho phép và có backoff |
| Đã ghi một phần rồi mất kết nối | Xác minh trạng thái, idempotency hoặc compensation trước retry |
| Input vi phạm hợp đồng | Sửa caller/input, không tự retry cùng tham số |
| Dependency cố định đang bị thiếu cấu hình | Alert/configuration fix, không retry vô hạn |

**Một API rõ loại failure là điều kiện thuận lợi cho phục hồi**, nhưng vẫn cần chính sách ngoài chữ ký `throws`.

## 26. Những lỗi thiết kế thường gặp

| Sai lầm | Vì sao nguy hiểm | Cách sửa |
| --- | --- | --- |
| Mọi method đều `throws Exception` | Hợp đồng quá rộng; caller phải xử lý chung | Chọn checked types cụ thể hoặc domain exception |
| `catch(Exception) { return null; }` | Che lỗi, lẫn null thành công | Báo failure đúng hợp đồng hoặc fallback thực |
| `catch(Exception) { retry(); }` | Retry cả lỗi input/bug không phục hồi | Retry có phân loại và giới hạn |
| Public domain API phơi `SQLException` không cần thiết | Gắn caller vào JDBC internals | Dịch ở tầng repository, giữ cause |
| Bao `IOException` bằng `new Exception(message)` | Mất loại lỗi có ý nghĩa, có thể mất cause | Chọn subtype/domain checked có cause |
| Tạo class exception mới cho mỗi message | Taxonomy phình to, caller không khác xử lý | Nhóm theo chiến lược xử lý, typed code khi hợp |
| Chọn subclass checked hẹp quá mức để “chính xác” | Khó mở rộng khi API có nhóm lỗi liên quan | Chọn superclass đủ đúng abstraction |
| Quên `throws` từ `close()` resource | Compile error hoặc xử lý thiếu | Dùng `Closeable`/hợp đồng cleanup rõ |
| Dùng `throws Exception` chỉ để xử lý callback `Function` | Không thay đổi `Function.apply` | Bắt trong lambda hoặc callback typed |
| Implementation override dùng `throws Exception` khi interface `throws IOException` | Vi phạm quy tắc checked overriding | Giữ cùng loại/subtype hoặc bớt checked |
| Đổi API thêm checked exception mà không cập nhật caller | Source compatibility có thể vỡ | Quản lý thay đổi version/changelog |
| Cho rằng bỏ bớt `throws` không ảnh hưởng source | Catch checked cũ có thể unreachable | Kiểm tra caller biên dịch lại |
| Log chỉ `e.getMessage()` khi dịch lỗi | Mất stack/cause | Giữ Throwable làm cause, log đúng API |
| Cast mọi `getCause()` sang một type hạ tầng | Implementation thay đổi gây lỗi cast | Dùng `instanceof` hoặc không phụ thuộc nội bộ |
| Dùng `RuntimeException` chung cho mọi failure | Caller khó phân loại, có thể mất semantics | Chọn unchecked subtype có ý nghĩa khi cần |
| Bắt `Throwable` để thay `catch(Exception)` | Bắt cả `Error` nghiêm trọng | Chỉ boundary đặc biệt mới cân nhắc |
| Ném `Error` cho lỗi validation | Sai phân cấp và ý nghĩa | `IllegalArgumentException`/result phù hợp |
| Không document unchecked errors | Caller không biết tiền điều kiện | Javadoc `@throws` và validation |
| Test dựa trên message để phân nhánh | Text dễ đổi | Test type/code/context/cause |
| Giữ token/password trong exception | Log có thể rò rỉ | Context tối thiểu, thông điệp an toàn |

## 27. Quy trình lựa chọn mệnh đề `throws` cho một API mới

Khi thiết kế một method:

1. **Viết mục đích method** bằng một câu ở mức người dùng API.
2. **Liệt kê các đường thất bại** có thể thấy trong hợp đồng, không chỉ từng exception từ implementation hiện tại.
3. **Phân loại failure dự kiến**: input sai, không tìm thấy, I/O, parse, resource tạm thời, trạng thái bất hợp lệ, lỗi nội bộ.
4. **Xác định caller nào có thể làm gì**: fallback, sửa input, retry, rollback, báo lỗi hay kết thúc.
5. **Chọn checked vs unchecked vs result** theo semantics của thao tác, không theo tiện compiler.
6. **Chọn loại đủ hẹp và ổn định**: nhóm JDK phù hợp hoặc custom domain exception cần thiết.
7. **Dịch exception tầng thấp tại boundary** nếu không nên để chi tiết implementation lộ ra public API; luôn giữ cause.
8. **Viết `throws` và Javadoc `@throws`** mô tả nguyên nhân/hợp đồng, kể cả các điều kiện unchecked đáng chú ý.
9. **Kiểm tra interface override và callback APIs**: implementation không được rộng checked throws; lambda bị ràng buộc target functional type.
10. **Viết test** xác nhận exception type, cause, thông tin có kiểu, đường thành công và failure.
11. **Xem tương thích API** khi dự kiến phát hành phiên bản mới; checked throws tác động caller lúc biên dịch.
12. **Không thêm loại checked “phòng hờ”** chỉ vì tương lai có thể có lỗi khác. Nếu phạm vi thay đổi có thể dự báo, chọn một abstraction hợp nghĩa.

### 27.1. Ba câu tự kiểm tra

- Nếu người dùng thấy `throws Exception`, họ có biết **loại failure và chính sách xử lý** không?
- Nếu tôi thay implementation hạ tầng, chữ ký API có cần đổi không? Nếu có, đó có thể là leak abstraction.
- Nếu gọi qua interface hoặc callback, mệnh đề checked throws của tôi **có thật sự hợp đồng tương thích** không?

Nếu câu trả lời chưa tốt, hãy xem lại taxonomy hoặc API boundary.

## 28. Kiểm thử hợp đồng ngoại lệ

Một test tốt kiểm tra **loại ngoại lệ và nguyên nhân**, không chỉ “bất kỳ Exception nào cũng được”.

Ví dụ JUnit 5:

```java
import static org.junit.jupiter.api.Assertions.*;
import java.io.IOException;
import org.junit.jupiter.api.Test;

class SpecificThrowsContractTest {
    @Test
    void reportsSpecificIOException() {
        IOException e = assertThrows(IOException.class,
                () -> SpecificFileContractDemo.read("offline"));
        assertEquals("Thiết bị không sẵn sàng", e.getMessage());
    }

    @Test
    void translatesButPreservesCause() {
        var error = assertThrows(
                ExceptionTranslationDemo.CatalogUnavailableException.class,
                ExceptionTranslationDemo::loadCatalog);
        assertInstanceOf(java.sql.SQLException.class,
                error.getCause());
    }

    @Test
    void separatesFormatFromIo() {
        assertThrows(
                TwoSpecificFailuresDemo.InvalidRecordException.class,
                () -> TwoSpecificFailuresDemo.load("oops"));
    }
}
```

Đây là **một file test JUnit Jupiter**, không chạy độc lập bằng `javac` chỉ có JDK; cần JUnit 5 và các demo classes ở cùng package (hoặc điều chỉnh visibility/package). `assertThrows` kiểm tra subtype quan hệ kế thừa; ở những API có hợp đồng rất cụ thể, có thể dùng `assertThrowsExactly` của JUnit phiên bản phù hợp.

**Kiểm tra cả kết quả thành công**, không chỉ thất bại. Đối với dịch exception, xác minh `getCause()` là loại/đối tượng mong đợi, và dữ liệu domain không bị báo là thành công khi tầng dưới ném lỗi.

### 28.1. Test source-level API compatibility

Với thư viện công khai, có thể duy trì các **compile-time contract tests**: caller mô phỏng viết handler cho những checked types được API công bố. Khi đổi clause `throws`, kiểm tra các module downstream có biên dịch lại không. Một unit test runtime đơn lẻ không phát hiện mọi thay đổi source-level của hợp đồng checked exception.

## 29. Câu hỏi thường gặp

### 29.1. Viết `throws Exception` có “sai Java” không?

Không. Hoàn toàn hợp lệ về cú pháp. Vấn đề chủ yếu là **thiết kế hợp đồng**, nhất là public/library API cần caller xử lý failure chính xác.

### 29.2. `throws IOException, SQLException` có được không?

Có, nếu method thực sự công bố hai checked failure và chúng phù hợp với abstraction/override contract. Nhưng ở boundary domain có thể muốn dịch chúng thành một hoặc nhiều exception domain phù hợp để tránh lộ tầng hạ tầng.

### 29.3. Chỉ có `IOException` hiện tại, khai `throws Exception` để dễ nâng cấp sau này được không?

Có thể về cú pháp nhưng thường **không nên** nếu không có lý do hợp đồng. Nó khiến mọi caller chịu loại checked rộng ngay từ đầu. Hãy thiết kế abstraction ổn định theo nhóm lỗi thực tế; quản lý API evolution khi thêm failure mới.

### 29.4. Khai `throws IOException` có ngăn `NullPointerException` không?

Không. `NullPointerException` là unchecked, vẫn có thể xảy ra. `throws` chủ yếu tham gia luật compile-time của checked exceptions.

### 29.5. Tại sao `catch(Exception)` có thể che bug?

Vì `RuntimeException extends Exception`. Nếu handler catch rộng rồi retry/fallback mà không phân loại, nó có thể nuốt cả `NullPointerException` hoặc `IllegalStateException` vốn báo vấn đề lập trình/trạng thái.

### 29.6. Khi nào cần custom exception?

Khi caller cần một phân loại failure **có ngữ nghĩa domain** và hợp đồng JDK không thể hiện đúng, hoặc khi bạn muốn tránh làm lộ exception hạ tầng. Không tạo custom class chỉ để bọc mỗi `IOException` nếu API I/O thuần có thể dùng `IOException` trực tiếp.

### 29.7. Tại sao không chỉ dùng `RuntimeException` cho mọi thứ?

Mặc dù giảm nghĩa vụ compile-time, điều đó có thể làm mất hợp đồng failure mà caller cần xử lý. Checked vs unchecked là quyết định theo API design, không phải lựa chọn “Java hiện đại luôn bỏ checked”.

### 29.8. `throws Exception` có bao gồm `Error` không?

Không. `Error` là nhánh khác dưới `Throwable`. `throws Exception` không phải hợp đồng cho mọi `Throwable`; `catch(Exception)` cũng không bắt `Error`. `throws Throwable` còn rộng hơn và thường không hợp lý với API ứng dụng.

### 29.9. Nếu thêm `throws IOException` vào method interface, mọi implementation phải kê không?

Không. Implementation có thể khai báo ít checked exceptions hơn hoặc không khai báo gì, nhưng không được mở rộng vượt hợp đồng. Caller qua interface vẫn bị compiler kiểm tra theo chữ ký interface.

### 29.10. Javadoc có cần mô tả unchecked exception?

Nên ghi những điều kiện vi phạm hợp đồng quan trọng qua `@throws`, dù unchecked type không bắt buộc xuất hiện ở clause `throws`. Tài liệu rõ giúp caller biết tiền điều kiện.

## 30. Bài tập tự luyện

### Bài 1 — Thu hẹp API đọc file

Một method đang dùng `String read(Path) throws Exception` nhưng chỉ gọi `Files.readString`. Hãy chọn `throws IOException` và cập nhật caller. Vì sao `IOException` phù hợp hơn `Exception` mà vẫn bao phủ cả `FileNotFoundException` subtype?

### Bài 2 — Hai loại lỗi không liên quan

Viết method `importText(String) throws IOException, ParseException`, mô phỏng input “offline” và “bad-format”. Viết caller có hai catch riêng rồi đổi sang multi-catch khi chính sách xử lý giống nhau.

### Bài 3 — Dịch lỗi JDBC

Mô phỏng `SQLException` ở tầng repository, chuyển sang `CatalogUnavailableException` ở tầng domain. Test `getCause()` là `SQLException`; không để caller phụ thuộc `SQLState` như một phần business contract nếu không có nhu cầu.

### Bài 4 — Checked vs unchecked

Một method nhận giá trị phần trăm và gọi nguồn cấu hình có thể ném `IOException`. Nên xử lý `percent = -1` bằng loại nào? Nên công bố `IOException` ra sao? Giải thích vì sao `throws Exception` không bắt buộc.

### Bài 5 — Interface override

Interface `Loader.load() throws IOException`, implementation `throws FileNotFoundException` có hợp lệ không? Nếu đổi implementation thành `throws Exception` thì sao? Giải thích bằng quan hệ subtype.

### Bài 6 — Thay đổi API v2

Phiên bản 1 công bố `throws ParseException`; phiên bản 2 thêm `throws IOException`. Hãy viết một caller phiên bản 1 sẽ không biên dịch lại được nếu không cập nhật handler. Nêu tác động source compatibility.

### Bài 7 — Catch rộng ở boundary

Trong một CLI dispatcher, `catch(Exception)` có thể dùng để log rồi trả exit code lỗi. Vì sao không nên áp cùng catch rồi trả `null` ở mọi repository/service? `Error` có bị catch không?

### Bài 8 — Resource close

Thay `Closeable` trong `CloseableSpecificThrowsDemo` bằng kiểu tĩnh `AutoCloseable` và kiểm tra nghĩa vụ checked của `close() throws Exception`. Tìm cách dùng type/adapter phù hợp để không khai `throws Exception` không cần thiết.

### Bài 9 — Generic callback

Tạo `CheckedSupplier<T,E extends Exception>` nhận lambda ném `IOException`. Viết `execute(...) throws E`; so sánh với `java.util.function.Supplier` vốn không khai checked throws.

### Bài 10 — Một lỗi domain là kết quả bình thường?

Một form có ba field sai. Thảo luận vì sao trả `ValidationResult` gồm ba issue có thể rõ hơn việc ném ba exception. Khi nào một custom checked exception vẫn có ý nghĩa?

### Bài 11 — Test hợp đồng

Viết JUnit test xác nhận method `read("offline")` ném `IOException`, method `load("oops")` ném custom checked, và exception translation giữ `cause`. Đừng chỉ viết `assertThrows(Exception.class, ...)` cho tất cả test.

### Bài 12 — Nâng cấp library

Giả sử một public API đang `throws Exception` và bạn muốn thu hẹp sang `throws IOException`. Thử recompile caller có `catch(SQLException)` rồi `catch(Exception)`; xem handler nào có thể trở nên không reachable và cần refactor.

## 31. Checklist thiết kế API trước khi phát hành

- [ ] Tôi xác định được **những checked failures thực sự thuộc hợp đồng**, không chỉ những exception từ code nội bộ chưa được phân loại?
- [ ] Có thể thay `throws Exception` bằng loại JDK cụ thể như `IOException`/`ParseException` không?
- [ ] Nếu API domain không nên lộ JDBC/HTTP internals, tôi có một exception domain có nghĩa không?
- [ ] Khi dịch lỗi, tôi đã truyền `cause` để không mất stack trace gốc chưa?
- [ ] Caller có thể phân biệt các lỗi có **chính sách xử lý khác nhau** không?
- [ ] Tôi phân biệt checked exception, unchecked exception và `Error` chưa?
- [ ] API chỉ kê checked exception cần thiết; không công bố loại quá rộng để “phòng hờ” chứ?
- [ ] Loại exception đã chọn có đủ ổn định nếu implementation thay đổi không?
- [ ] Tôi không tạo taxonomy quá sâu hoặc một custom `ApplicationException` quá rộng vô nghĩa chứ?
- [ ] Tôi đã viết Javadoc `@throws` cho điều kiện failure và tiền điều kiện quan trọng chưa?
- [ ] Nếu method override interface, `throws` có tương thích với hợp đồng cấp cha chưa?
- [ ] Nếu dùng functional interface chuẩn, tôi đã hiểu hạn chế checked throws của callback chưa?
- [ ] Nếu dùng try-with-resources, đã xét checked exceptions từ `close()` chưa?
- [ ] Tôi không coi mọi `IOException` tự động retryable, mọi validation error phải ném, hay mọi bug có thể phục hồi chứ?
- [ ] Không có `catch(Exception)` ở tầng thấp âm thầm trả null/false/success?
- [ ] Nếu public API thay đổi checked throws, tôi đã xem xét tương thích source và migration chưa?
- [ ] Tôi đã test failure type, message có ý nghĩa, cause, success path và trạng thái sau lỗi chưa?
- [ ] Ngoại lệ và log không chứa dữ liệu bí mật hoặc nội dung raw của request không cần thiết?
- [ ] Có một boundary chịu trách nhiệm chuyển lỗi thành phản hồi API/CLI an toàn không?
- [ ] Tôi đã cân nhắc result type nếu failure là kết quả dự kiến thường xuyên chưa?

## 32. Tổng kết

`throws Exception` không sai cú pháp, nhưng thường là **hợp đồng quá rộng** cho một API cụ thể. Dùng `throws IOException` cho thao tác I/O, nhiều checked types rõ ràng nếu caller cần phân biệt, hoặc custom domain exception khi muốn ẩn chi tiết tầng dưới mà vẫn **giữ `cause`**. Không cần kê unchecked exception chỉ để compiler chấp nhận; thay vào đó, document tiền điều kiện. Checked `throws` ảnh hưởng caller, override, generic callback và sự tương thích khi nâng phiên bản, nên phải chọn loại **đủ hẹp, có ngữ nghĩa và ở đúng mức abstraction**. `throws Exception` vẫn có chỗ đứng trong callback/framework tổng quát và demo đơn giản, nhưng không nên dùng nó như lựa chọn mặc định cho mọi method.