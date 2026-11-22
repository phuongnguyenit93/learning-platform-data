# Java 7 — Multi-catch: Giới hạn quan hệ cha con giữa các kiểu được kết hợp

## 1. Quy tắc cốt lõi

Từ Java 7, một khối `catch` có thể xử lý **nhiều kiểu ngoại lệ** bằng cú pháp `catch (A | B | C e)`. Điều kiện quan trọng là **không có hai kiểu nào trong cùng danh sách alternatives mà một kiểu là kiểu con (subtype) của kiểu còn lại**.

Ví dụ:

- **Hợp lệ:** `catch (IOException | SQLException e)` vì `IOException` và `SQLException` đều là các nhánh khác nhau của `Exception`; không kiểu nào kế thừa kiểu kia.
- **Không hợp lệ:** `catch (FileNotFoundException | IOException e)` vì `FileNotFoundException extends IOException`.
- **Không hợp lệ:** `catch (IOException | Exception e)` vì `IOException extends Exception`.
- **Hợp lệ về quan hệ kiểu:** `catch (FileNotFoundException | EOFException e)` vì hai lớp này đều là con của `IOException` nhưng **không** phải cha/con của nhau. Việc khối `try` có thể ném cả hai ngoại lệ checked hay không là một kiểm tra khác.

Đây là **quy tắc biên dịch**, có hiệu lực trong Java hiện đại, không phải hành vi chỉ tồn tại ở Java 7. Quy tắc này được mô tả tại [Java Language Specification §14.20 — The try statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20).

### 1.1. Sơ đồ phân cấp để nhìn rõ quan hệ

```text
Throwable
├── Exception
│   ├── IOException
│   │   ├── FileNotFoundException
│   │   ├── EOFException
│   │   └── FileSystemException
│   │       └── NoSuchFileException
│   ├── SQLException
│   └── RuntimeException
│       ├── IllegalArgumentException
│       │   └── NumberFormatException
│       └── IllegalStateException
└── Error
```

Đọc sơ đồ theo hai hướng:

1. **Một lớp con nằm trong phạm vi bắt của lớp cha.** `catch (IOException e)` đã bắt được `FileNotFoundException`, `EOFException` và `NoSuchFileException`.
2. **Hai nhánh cùng có một tổ tiên không có nghĩa là chúng có quan hệ cha/con với nhau.** `FileNotFoundException` và `EOFException` đều kế thừa `IOException` nhưng không kế thừa nhau, nên có thể đứng chung trong multi-catch nếu cả hai là trường hợp có thể xảy ra.

Quy tắc áp dụng cho **quan hệ kế thừa gián tiếp**, không chỉ `extends` trực tiếp. Ví dụ `NoSuchFileException` là hậu duệ của `IOException` thông qua `FileSystemException`; vì thế `catch (NoSuchFileException | IOException e)` vẫn không hợp lệ.

## 2. Vì sao Java cấm cha và con trong cùng multi-catch?

Giả sử có code sau (cố ý **không biên dịch được**):

```java
try {
    throw new java.io.FileNotFoundException("report.csv");
} catch (java.io.FileNotFoundException | java.io.IOException e) {
    System.err.println(e.getMessage());
}
```

`FileNotFoundException` đã là một dạng `IOException`. Nếu ngoại lệ là `FileNotFoundException` thì nhánh `IOException` cũng khớp; khai báo hai alternative trong cùng một `catch` trở thành dư thừa theo quan hệ kiểu.

Trình biên dịch **từ chối ngay cả khi bạn đảo thứ tự**:

```java
try {
    throw new java.io.FileNotFoundException("report.csv");
} catch (java.io.IOException | java.io.FileNotFoundException e) {
    System.err.println(e.getMessage());
}
```

Đổi thứ tự không làm mất quan hệ subtype. Bản thân cú pháp `|` ở đây biểu diễn **một hợp các kiểu ngoại lệ** (union), không phải một danh sách xử lý theo độ ưu tiên. Nếu muốn khác biệt hành vi theo từng subtype, phải dùng các `catch` tách biệt theo thứ tự thích hợp.

Thông báo compiler thường có nội dung gần như **“Alternatives in a multi-catch statement cannot be related by subclassing”**; từ ngữ cụ thể có thể khác theo phiên bản JDK. Đây là lỗi ở **compile-time**: chương trình không tạo class file hợp lệ để chạy.

## 3. Phân biệt ba tình huống: cha-con, anh-em và không cùng nhánh gần

| Alternative A | Alternative B | Trong cùng `catch (A | B e)`? | Lý do |
| --- | --- | --- | --- |
| `FileNotFoundException` | `IOException` | **Không** | A là subtype của B. |
| `IOException` | `Exception` | **Không** | A là subtype của B. |
| `NoSuchFileException` | `IOException` | **Không** | A là subtype gián tiếp của B. |
| `NumberFormatException` | `IllegalArgumentException` | **Không** | A là subtype của B. |
| `IllegalArgumentException` | `RuntimeException` | **Không** | A là subtype của B. |
| `IOException` | `SQLException` | **Có** | Hai nhánh khác nhau dưới `Exception`. |
| `FileNotFoundException` | `EOFException` | **Có** | Cả hai dưới `IOException` nhưng không là subtype của nhau. |
| `IllegalArgumentException` | `IllegalStateException` | **Có** | Hai nhánh khác nhau dưới `RuntimeException`. |
| `IOException` | `SecurityException` | **Có** | Không có quan hệ cha/con; cân nhắc chính sách xử lý checked/unchecked cho phù hợp. |
| `IOException` | `IOException` | **Không** | Lặp lại cùng một kiểu, không tạo thêm trường hợp mới. |

**Lưu ý:** “Có” trong bảng chỉ có nghĩa **vượt qua điều kiện quan hệ kiểu**. Một chương trình còn phải vượt qua kiểm tra *checked exception*, phạm vi ngoại lệ có thể được ném trong `try`, và các `catch` trước đó. Ví dụ, nếu `try` hoàn toàn không có đường đi nào có thể ném `SQLException`, compiler có thể báo rằng `SQLException` checked không bao giờ được ném và từ chối multi-catch đó. Vì vậy **“hai kiểu không kế thừa nhau” là điều kiện cần chứ chưa đủ** để mọi đoạn mã biên dịch.

## 4. Các cách sửa đúng theo ý nghĩa nghiệp vụ

### Cách A — Nếu cùng cách xử lý, bắt một kiểu cha phù hợp

Khi các ngoại lệ con của `IOException` **đều cần cùng một chính sách**, chỉ bắt `IOException`:

```java
try {
    java.nio.file.Files.readString(java.nio.file.Path.of("config.txt"));
} catch (java.io.IOException e) {
    System.err.println("Cannot read config: " + e.getMessage());
}
```

Đoạn mã đặt trong một phương thức; tên tệp là ví dụ. Nó dùng `Files.readString` có trên JDK 17+. `IOException` bao phủ `NoSuchFileException`, `FileNotFoundException` và các hậu duệ khác trong nhóm I/O nếu chúng phát sinh. Không cần liệt kê `IOException | NoSuchFileException`.

**Đổi lại:** kiểu cha rộng hơn có thể bắt cả các lỗi I/O mà lúc đầu bạn chưa nghĩ tới. Đây là quyết định chính sách: nếu mọi I/O failure đều được xử lý cùng cách, bắt cha hợp lý; nếu mỗi loại cần hành vi khác nhau, xem cách B.

### Cách B — Nếu cách xử lý khác nhau, dùng nhiều khối `catch`

Có thể dùng **nhiều `catch` riêng**, đặt subtype cụ thể **trước** supertype:

```java
try {
    java.nio.file.Files.readString(java.nio.file.Path.of("config.txt"));
} catch (java.nio.file.NoSuchFileException e) {
    System.err.println("Config file is missing");
} catch (java.io.IOException e) {
    System.err.println("Other I/O error: " + e.getMessage());
}
```

Trường hợp tệp không tồn tại được xử lý chuyên biệt, các lỗi I/O khác được xử lý ở nhánh rộng hơn. Nếu đảo thứ tự:

```java
try {
    java.nio.file.Files.readString(java.nio.file.Path.of("config.txt"));
} catch (java.io.IOException e) {
    System.err.println("I/O failure");
} catch (java.nio.file.NoSuchFileException e) {
    System.err.println("Missing file");
}
```

Đoạn thứ hai **cố ý không biên dịch** vì khối `catch (IOException)` trước đã bắt mọi `NoSuchFileException`. Đây là lỗi về **thứ tự giữa các khối catch**, khác với lỗi **cha/con bên trong một multi-catch**. Khi tách khối, subtype đứng trước supertype; khi gộp bằng `|`, subtype và supertype **không thể** đứng chung ở bất kỳ thứ tự nào.

### Cách C — Nếu hai ngoại lệ thuộc nhánh độc lập và xử lý giống nhau, dùng multi-catch

```java
try {
    java.nio.file.Files.readString(java.nio.file.Path.of("config.txt"));
    databaseOperation();
} catch (java.io.IOException | java.sql.SQLException e) {
    System.err.println("Operation failed: " + e.getMessage());
}
```

Đây là **mã minh họa trong một phương thức** có `databaseOperation()` được định nghĩa ở dự án và có thể ném `SQLException`. Cả `IOException` và `SQLException` đều là checked exceptions không có quan hệ cha/con. Nếu hai lỗi có cùng hành vi (ví dụ log với mã lỗi nhất quán rồi trả failure), multi-catch giảm trùng lặp.

Trong ứng dụng thực tế, tránh gom một khối `try` quá dài nếu khó phân biệt thao tác nào thất bại. Dùng ngoại lệ cụ thể, có ngữ cảnh và thông báo thích hợp khi đi qua ranh giới service/API.

### Cách D — Muốn ghép các subtype anh-em thì kiểm tra cả khả năng ném exception

Hai lớp `FileNotFoundException` và `EOFException` đều dưới `IOException` nhưng không dưới nhau, nên có thể dùng:

```java
static void readSample(boolean missing)
        throws java.io.FileNotFoundException, java.io.EOFException {
    if (missing) {
        throw new java.io.FileNotFoundException("missing.txt");
    }
    throw new java.io.EOFException("unexpected EOF");
}

static void handleSample(boolean missing) {
    try {
        readSample(missing);
    } catch (java.io.FileNotFoundException | java.io.EOFException e) {
        System.err.println(e.getClass().getSimpleName() + ": " + e.getMessage());
    }
}
```

Đây là **hai phương thức cần đặt trong một lớp**, không phải file Java độc lập. Cả hai checked exception có thể được ném từ `readSample`, nên không bị loại bởi kiểm tra “không bao giờ ném”. Nếu nhiều subtype dùng chung cách xử lý và **không cần phân biệt chúng**, bắt `IOException` cũng là lựa chọn đơn giản; chỉ liệt kê subtype khi muốn giới hạn cụ thể tập lỗi được xử lý.

## 5. Chương trình Java 17+ hoàn chỉnh

Ví dụ độc lập dưới đây có đúng hai nguồn lỗi checked: đọc tệp thất bại bằng một `FileNotFoundException` (một subtype của `IOException`) và lỗi thao tác dữ liệu bằng `SQLException` (nhánh khác của `Exception`). Hai loại được xử lý bằng một `catch` hợp lệ.

Tạo file **`MultiCatchHierarchyDemo.java`**:

```java
import java.io.FileNotFoundException;
import java.io.IOException;
import java.sql.SQLException;

public class MultiCatchHierarchyDemo {
    static void perform(String task) throws IOException, SQLException {
        switch (task) {
            case "read" -> throw new FileNotFoundException("report.csv");
            case "query" -> throw new SQLException("database unavailable");
            default -> { }
        }
    }

    static String run(String task) {
        try {
            perform(task);
            return "success";
        } catch (IOException | SQLException ex) {
            return ex.getClass().getSimpleName() + ": " + ex.getMessage();
        }
    }

    public static void main(String[] args) {
        System.out.println("read -> " + run("read"));
        System.out.println("query -> " + run("query"));
        System.out.println("other -> " + run("other"));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac --release 17 MultiCatchHierarchyDemo.java
java MultiCatchHierarchyDemo
```

**Stdout chính xác:**

```text
read -> FileNotFoundException: report.csv
query -> SQLException: database unavailable
other -> success
```

Giải thích chi tiết:

1. `perform` khai báo `throws IOException, SQLException`. Nhánh `"read"` ném một đối tượng `FileNotFoundException`, là con của `IOException`; nhánh `"query"` ném `SQLException`.
2. Trong `run`, `catch (IOException | SQLException ex)` hợp lệ vì hai alternatives không có quan hệ subtype với nhau. `FileNotFoundException` được bắt thông qua kiểu cha `IOException`, còn `SQLException` được bắt trực tiếp.
3. `ex.getClass().getSimpleName()` phản ánh **kiểu thực tế** của đối tượng lỗi ở runtime, nên dòng đầu có tên `FileNotFoundException`, dù không liệt kê subtype đó trong multi-catch.
4. Nhánh `"other"` không ném ngoại lệ và phương thức trả `"success"`.
5. Cú pháp switch arrow `->` được dùng cho ví dụ Java 17; nó được chuẩn hóa ở Java 14. **Quy tắc multi-catch về quan hệ kiểu vẫn là quy tắc từ Java 7 và còn áp dụng trên JDK hiện đại.**

Ví dụ cố tình **ném ngoại lệ bằng mã** để kết quả có thể kiểm chứng mà không cần database hoặc file thật. Ứng dụng thực tế phải gắn các thao tác với I/O/DB thật và quản lý resource bằng try-with-resources khi phù hợp.

## 6. Quy tắc kiểu của biến `catch` và ảnh hưởng của quan hệ kế thừa

Trong:

```java
catch (IOException | SQLException ex) {
    System.err.println(ex.getMessage());
}
```

`ex` có **kiểu khai báo chung được trình biên dịch suy ra từ các alternative** (theo quy tắc *least upper bound*, LUB); đối tượng thực tế ở runtime vẫn có kiểu gốc. Vì thế:

- Các thao tác chung như `ex.getMessage()`, `ex.getCause()`, `ex.getClass()` hoặc `ex.printStackTrace()` sử dụng được.
- Không thể giả định `ex` luôn là `SQLException` để gọi phương thức chỉ thuộc `SQLException` nếu chưa xác định kiểu. Nếu thật sự cần hành vi riêng, tách `catch` hoặc kiểm tra loại ở ranh giới thích hợp.
- **Biến `ex` trong multi-catch là `final` ngầm định.** Viết `ex = new IOException();` trong khối `catch (IOException | SQLException ex)` là lỗi biên dịch. Quy tắc này không phụ thuộc quan hệ kiểu; nó là đặc tính chung của multi-catch.
- Các alternative đều phải là kiểu ngoại lệ hợp lệ (`Throwable` hoặc subtype của `Throwable`). Không thể đặt `String`, kiểu primitive hoặc type variable bất kỳ vào vị trí kiểu bắt ngoại lệ.

Không nên dùng `catch (Exception e)` chỉ để né lỗi quan hệ kiểu trong mọi trường hợp: `Exception` có thể bắt rộng hơn ý định, bao gồm nhiều `RuntimeException` phản ánh bug lập trình. Hãy chọn tầng xử lý và kiểu ngoại lệ theo hợp đồng.

## 7. Hai kiểm tra biên dịch khác cần phân biệt

### 7.1. Ngoại lệ checked có thật sự có thể được ném?

Ví dụ sau **cố ý sai** vì `SQLException` là checked exception mà `try` không có thao tác nào có thể ném:

```java
try {
    System.out.println("hello");
} catch (java.sql.SQLException e) {
    System.err.println(e.getMessage());
}
```

Đó là lỗi **khả năng ném exception** (*exception analysis*), không phải lỗi cha/con trong multi-catch. Nếu thêm `SQLException` vào một multi-catch mà `try` không thể ném nó, điều kiện quan hệ kiểu có thể vẫn đạt nhưng mã vẫn không được biên dịch.

Với `RuntimeException` (unchecked), compiler không luôn yêu cầu chứng minh `try` có thể ném chính xác kiểu đó; nhưng bắt rộng các unchecked exception chỉ để tránh khai báo lỗi thường làm che nguyên nhân bug và giảm tính rõ ràng của thiết kế.

### 7.2. Một khối `catch` trước đã bắt ngoại lệ chưa?

Một `try` có thể có nhiều `catch`. Compiler còn kiểm tra một alternative ở khối sau có bị khối trước bao phủ hay không. Ví dụ:

```java
try {
    java.nio.file.Files.readString(java.nio.file.Path.of("config.txt"));
} catch (java.io.IOException e) {
    System.err.println("I/O error");
} catch (java.nio.file.NoSuchFileException | java.io.EOFException e) {
    System.err.println("More specific I/O error");
}
```

Đoạn này **cố ý sai**: `IOException` ở catch trước đã bao phủ hai subtype ở catch sau. Dù `NoSuchFileException` và `EOFException` không có quan hệ subtype với nhau, khối sau vẫn không thể nhận các trường hợp đó sau catch cha.

Khi kiểm tra multi-catch, hãy làm theo **thứ tự hai lớp**: (1) trong chính danh sách `A | B | C` có cặp cha/con nào không; (2) mỗi alternative có thể xuất hiện từ `try` và chưa bị catch trước chặn hết hay không.

## 8. Tự tạo exception trong dự án: quan hệ gián tiếp cũng tính

Giả sử ứng dụng có phân cấp ngoại lệ của mình:

```java
class ApplicationException extends Exception {
    ApplicationException(String message) {
        super(message);
    }
}

class ValidationException extends ApplicationException {
    ValidationException(String message) {
        super(message);
    }
}

class PaymentValidationException extends ValidationException {
    PaymentValidationException(String message) {
        super(message);
    }
}

class RemoteServiceException extends ApplicationException {
    RemoteServiceException(String message) {
        super(message);
    }
}
```

Đây là **các khai báo lớp minh họa**, đặt ở cùng tệp Java không có lớp `public` nếu muốn chạy thử. Xét các cách bắt:

| Kết hợp | Hợp lệ về subtype? | Giải thích |
| --- | --- | --- |
| `ValidationException | PaymentValidationException` | **Không** | `PaymentValidationException` là subtype trực tiếp của `ValidationException`. |
| `ApplicationException | PaymentValidationException` | **Không** | Có quan hệ subtype **gián tiếp**. |
| `ValidationException | RemoteServiceException` | **Có** | Là hai nhánh khác nhau dưới `ApplicationException`. |
| `PaymentValidationException | RemoteServiceException` | **Có** | Không lớp nào kế thừa lớp kia. |

Nếu tất cả lỗi `ApplicationException` cùng cần log và trả mã lỗi ứng dụng, chỉ `catch (ApplicationException e)` có thể là đủ. Nếu **lỗi validation** cần phản hồi khác **lỗi dịch vụ bên ngoài**, dùng các `catch` riêng (hoặc multi-catch giữa những kiểu không liên hệ nếu thực sự xử lý cùng cách).

Không tạo một “superclass chung” chỉ để làm multi-catch hợp lệ; phân cấp exception nên phản ánh ý nghĩa nghiệp vụ và hành vi thực sự, không chỉ phục vụ cú pháp.

## 9. Quy trình sửa lỗi “Alternatives cannot be related by subclassing”

Khi nhận lỗi biên dịch cho `catch (A | B | C e)`:

1. **Mở định nghĩa và sơ đồ phân cấp exception.** Tìm mọi cặp alternative mà một kiểu `extends` kiểu kia, kể cả qua nhiều cấp; đừng chỉ nhìn tên lớp.
2. **Nếu cùng cách xử lý**, giữ kiểu cha phù hợp và loại kiểu con dư thừa khỏi union. Ví dụ `IOException | FileNotFoundException` → `IOException`.
3. **Nếu cách xử lý khác**, tách thành nhiều `catch`; xếp các kiểu chuyên biệt trước kiểu tổng quát.
4. **Nếu muốn giữ multi-catch**, chỉ kết hợp các kiểu không có quan hệ subtype với nhau. Các kiểu anh-em vẫn có thể kết hợp.
5. **Kiểm tra khả năng ném checked exception** trong `try` và thứ tự với các catch đứng trước; đây là những lỗi độc lập với quan hệ cha/con.
6. **Biên dịch trên JDK mục tiêu**, kiểm tra các nhánh lỗi bằng test và xác nhận exception được xử lý đúng mức nghiệp vụ. Chú ý giữ stack trace/cause khi chuyển ngoại lệ giữa các tầng thay vì chỉ ghi chuỗi lỗi.

### Các lỗi hiểu sai thường gặp

**“Đặt lớp con trước lớp cha trong `catch (Con | Cha e)` sẽ hợp lệ.”** Sai: điều kiện không phụ thuộc thứ tự trong union.

**“Hai lớp cùng kế thừa một cha thì không được multi-catch.”** Sai: chỉ cấm khi **một alternative là subtype của alternative kia**; hai kiểu anh-em vẫn hợp lệ.

**“Cùng là checked exception thì có thể luôn kết hợp.”** Sai: phải kiểm tra quan hệ subtype, khả năng ném từ `try` và thứ tự catch trước.

**“`IOException | FileNotFoundException` giúp bắt nhiều lỗi hơn `IOException`.”** Sai: mọi `FileNotFoundException` vốn đã là `IOException`.

**“Bắt `Exception` là cách sửa chuẩn cho mọi multi-catch lỗi.”** Không nên: nó mở rộng quá mức tập lỗi và có thể che đi bug nếu đặt sai tầng xử lý.

**“Runtime luôn biến exception thành kiểu cha khi bị catch qua kiểu cha.”** Sai: `ex` vẫn trỏ tới đối tượng nguyên thủy; `getClass()` và stack trace phản ánh kiểu thực tế.

**“Sửa danh sách subtype là đủ, không cần kiểm tra `try`.”** Sai: compiler còn kiểm tra checked exceptions thực sự có thể được ném hay không.

## 10. Câu hỏi tự kiểm tra

**1.** `catch (IOException | NoSuchFileException e)` hợp lệ không? — **Không**. `NoSuchFileException` là subtype gián tiếp của `IOException`.

**2.** `catch (FileNotFoundException | EOFException e)` có vượt qua điều kiện quan hệ kiểu không? — **Có**. Hai lớp là anh-em dưới `IOException`, nhưng `try` vẫn phải có khả năng ném cả hai checked exceptions.

**3.** Đổi `catch (IOException | FileNotFoundException e)` thành `catch (FileNotFoundException | IOException e)` có sửa lỗi không? — **Không**, thứ tự không làm mất quan hệ kế thừa.

**4.** Một phương thức có `catch (FileNotFoundException e)` rồi `catch (IOException e)`, có đúng không? — **Có thể đúng** nếu phần `try` có thể ném những loại I/O exception phù hợp. Đây là cách bắt cụ thể trước và tổng quát sau.

**5.** Với `catch (IOException | SQLException e)`, có được gán `e = new IOException()` trong khối không? — **Không**, biến multi-catch được khai báo `final` ngầm định.

**6.** `NumberFormatException | IllegalArgumentException` có hợp lệ không? — **Không**. `NumberFormatException extends IllegalArgumentException`.

**7.** Nếu hai lỗi cần hai phản hồi khác nhau, có nên cố gộp vào một multi-catch? — **Không cần**. Dùng hai khối catch riêng hoặc thiết kế xử lý phân nhánh có chủ đích.

## Tài liệu chính thức

- [JLS Java 17 §14.20 — The try statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20): định nghĩa multi-catch, ràng buộc cặp subtype và biến catch ngầm định `final`.
- [JLS Java 17 §11.2 — Compile-time checking of exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.2): phân tích checked exception, loại ngoại lệ có thể bắt và các catch trước.
- [dev.java — Catching and Handling Exceptions](https://dev.java/learn/catching-and-handling-exceptions/): ví dụ multi-catch và quy tắc các alternative không được kế thừa nhau.

**Ghi nhớ:** Trong **cùng một multi-catch**, các kiểu ngoại lệ phải **không có quan hệ cha/con với nhau**, kể cả gián tiếp. Nếu một kiểu đã bao phủ kiểu khác, bắt kiểu cha; nếu cần xử lý chuyên biệt, tách thành nhiều catch đúng thứ tự; nếu các kiểu thuộc các nhánh độc lập và cùng cách xử lý, multi-catch là lựa chọn phù hợp.