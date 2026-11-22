# Quan hệ kiểu cha, kiểu con và lựa chọn `catch` trong Java

Khi một ngoại lệ được ném, Java không tìm `catch` bằng cách so sánh **tên ngoại lệ trong thông điệp**. JVM xét **kiểu thực tế của đối tượng ngoại lệ** và quan hệ kế thừa với kiểu khai báo trong từng nhánh `catch`. Một nhánh bắt kiểu cha có thể bắt cả ngoại lệ thuộc kiểu con. Vì vậy, thứ tự `catch`, phạm vi `try` và tầng xử lý quyết định một lỗi sẽ được xử lý ra sao.

Bài này tập trung vào ba câu hỏi:

1. Ngoại lệ nào là **cha/con** trong hệ thống kiểu của Java?
2. Nếu cùng một lỗi phù hợp với nhiều kiểu `catch`, Java **chọn nhánh nào**?
3. Khi viết API và tổ chức tầng xử lý, nên bắt **kiểu cụ thể** hay **kiểu tổng quát**?

## 1. Cây phân cấp ngoại lệ cần nắm

Các ngoại lệ và lỗi nghiêm trọng trong Java đều thuộc phân cấp `java.lang.Throwable`. Một phần cây quan trọng:

```text
java.lang.Object
└── java.lang.Throwable
    ├── java.lang.Error
    │   ├── AssertionError
    │   ├── LinkageError
    │   └── VirtualMachineError
    │       └── OutOfMemoryError
    └── java.lang.Exception
        ├── java.io.IOException
        │   ├── java.io.FileNotFoundException
        │   └── java.io.EOFException
        ├── java.sql.SQLException
        ├── java.lang.InterruptedException
        └── java.lang.RuntimeException
            ├── java.lang.IllegalArgumentException
            │   └── java.lang.NumberFormatException
            ├── java.lang.IllegalStateException
            ├── java.lang.NullPointerException
            └── java.lang.IndexOutOfBoundsException
                └── java.lang.ArrayIndexOutOfBoundsException
```

Đây là **một phần của cây**, không phải mọi loại ngoại lệ trong Java. Từ sơ đồ:

- `Throwable` là kiểu cha chung; `Exception` và `Error` là hai nhánh con khác nhau.
- `IOException` là cha của `FileNotFoundException`; một handler khai báo `IOException` có thể bắt `FileNotFoundException`.
- `IllegalArgumentException` là cha của `NumberFormatException`; một handler khai báo `IllegalArgumentException` có thể bắt `NumberFormatException`.
- `Exception` là cha gián tiếp của `RuntimeException`, nhưng **không phải cha của `Error`**.
- `RuntimeException` và các lớp con thường là **unchecked exceptions**. `Error` và các lớp con cũng là unchecked theo quy tắc của Java, nhưng chúng không nên được xem như lỗi nghiệp vụ để bắt và phục hồi thông thường.
- Các lớp ngoại lệ thuộc `Exception` nhưng **không** thuộc `RuntimeException`, chẳng hạn `IOException`, là **checked exceptions**: trình biên dịch thường buộc mã gọi phải `catch` hoặc khai báo `throws`.

Quan hệ cha/con này là quan hệ **kế thừa lớp (`extends`)**, không phải dựa vào tên giống nhau. Chẳng hạn `NumberFormatException` kế thừa `IllegalArgumentException`, dù hai tên có vẻ mô tả các nguyên nhân khác nhau.

## 2. Quy tắc khớp kiểu: `catch (Parent ex)` bắt được đối tượng con

Giả sử tại runtime đang có đối tượng:

```java
NumberFormatException ex = new NumberFormatException("abc");
```

Đối tượng đó đồng thời tương thích với các kiểu tham chiếu `NumberFormatException`, `IllegalArgumentException`, `RuntimeException`, `Exception`, `Throwable` và `Object`. Trong một mệnh đề `catch`, kiểu tham số phải là `Throwable` hoặc lớp con của nó, nên không thể viết `catch (Object ex)`.

Nếu một vùng `try` có:

```java
try {
    Integer.parseInt("abc");
} catch (IllegalArgumentException ex) {
    System.out.println("Bắt bằng kiểu cha");
}
```

thì chương trình in:

```text
Bắt bằng kiểu cha
```

`Integer.parseInt("abc")` ném `NumberFormatException`, và `NumberFormatException` **là một** `IllegalArgumentException`. Vì thế nhánh khai báo kiểu cha khớp. Các đoạn này là ví dụ có thể đặt vào thân phương thức, không phải tệp chương trình độc lập.

Có thể diễn đạt quan hệ theo hướng sau:

- Khi đối tượng ngoại lệ là **con** của kiểu `catch`, handler có thể bắt nó.
- Khi kiểu `catch` là **con** của đối tượng ngoại lệ được ném thuộc kiểu cha, handler đó **không** bắt đối tượng cha chỉ vì có cùng họ.
- Hai kiểu nằm ở **hai nhánh không có quan hệ kế thừa với nhau** thì một handler của kiểu này không tự bắt kiểu kia. Ví dụ: `IOException` không bắt `NumberFormatException`.

**Kiểu runtime mới là yếu tố quyết định khi ném:** kể cả nếu một tham chiếu có kiểu khai báo `Exception`, nếu đối tượng thực tế là `NumberFormatException` thì handler phù hợp nhất trong chuỗi `catch` hợp lệ vẫn là handler có thể bắt `NumberFormatException`.

## 3. Thứ tự các nhánh `catch`: cụ thể trước, tổng quát sau

Một ngoại lệ có thể tương thích với nhiều kiểu, chẳng hạn `FileNotFoundException` cũng thuộc `IOException` và `Exception`. Nhưng khi có nhiều nhánh `catch` áp dụng cho **cùng một vùng `try`**, Java xét chúng **theo thứ tự từ trên xuống**. Nhánh khớp đầu tiên là nhánh xử lý. Vì thế:

```java
try {
    // Có thể ném FileNotFoundException hoặc IOException khác.
} catch (java.io.FileNotFoundException ex) {
    // Xử lý riêng trường hợp không tìm thấy tệp.
} catch (java.io.IOException ex) {
    // Xử lý các IOException còn lại.
}
```

Đây là cấu trúc minh họa (phần `try` cần thao tác I/O thực tế thì mới có tác dụng).

Nếu đảo lại:

```java
try {
    // Có thể ném IOException.
} catch (java.io.IOException ex) {
    // Bắt luôn cả FileNotFoundException.
} catch (java.io.FileNotFoundException ex) {
    // Không thể đến được: lỗi biên dịch.
}
```

Đoạn trên **cố ý không biên dịch**: `FileNotFoundException` đã bị handler `IOException` phía trước bao phủ hoàn toàn. Điều tương tự xảy ra khi đặt `catch (IllegalArgumentException)` trước `catch (NumberFormatException)`.

**Quy tắc thực hành:** trong cùng một chuỗi `catch`, đặt lớp ngoại lệ con trước lớp cha. Các nhánh anh em không kế thừa lẫn nhau, như `NumberFormatException` và một lớp con khác của `IllegalArgumentException`, không bắt buộc thứ tự tương đối vì quan hệ kế thừa; nên sắp xếp theo cách dễ đọc.

Thứ tự `catch` không phải một cuộc thi tìm kiểu “cụ thể nhất” tự động. Java đảm bảo bạn không đặt handler bị che khuất phía sau, sau đó chạy theo thứ tự handler được viết.

## 4. Ví dụ Java 17+ chạy được: chọn đúng nhánh theo phân cấp

Lưu chương trình hoàn chỉnh sau thành tệp **`CatchHierarchyDemo.java`**.

```java
import java.io.FileNotFoundException;
import java.io.IOException;

public class CatchHierarchyDemo {

    // Ngoại lệ nghiệp vụ là lớp con của IllegalArgumentException.
    static class InvalidQuantityException extends IllegalArgumentException {
        InvalidQuantityException(String message) {
            super(message);
        }
    }

    static void execute(String scenario) throws IOException {
        switch (scenario) {
            case "quantity" ->
                    throw new InvalidQuantityException("quantity <= 0");
            case "format" ->
                    throw new NumberFormatException("abc");
            case "argument" ->
                    throw new IllegalArgumentException("invalid argument");
            case "file" ->
                    throw new FileNotFoundException("config.txt");
            case "io" ->
                    throw new IOException("broken stream");
            default ->
                    System.out.println("execute: OK");
        }
    }

    static void handle(String scenario) {
        System.out.println("CASE " + scenario);
        try {
            execute(scenario);
            System.out.println("after execute");
        } catch (InvalidQuantityException ex) {
            System.out.println("catch InvalidQuantityException: "
                    + ex.getMessage());
        } catch (NumberFormatException ex) {
            System.out.println("catch NumberFormatException: "
                    + ex.getMessage());
        } catch (IllegalArgumentException ex) {
            System.out.println("catch IllegalArgumentException: "
                    + ex.getMessage());
        } catch (FileNotFoundException ex) {
            System.out.println("catch FileNotFoundException: "
                    + ex.getMessage());
        } catch (IOException ex) {
            System.out.println("catch IOException: "
                    + ex.getMessage());
        } finally {
            System.out.println("finally");
        }
    }

    public static void main(String[] args) {
        for (String scenario : new String[] {
                "ok", "quantity", "format", "argument", "file", "io"
        }) {
            handle(scenario);
        }
    }
}
```

Biên dịch và chạy bằng **JDK 17 trở lên**:

```bash
javac -encoding UTF-8 CatchHierarchyDemo.java
java CatchHierarchyDemo
```

**Stdout chính xác**:

```text
CASE ok
execute: OK
after execute
finally
CASE quantity
catch InvalidQuantityException: quantity <= 0
finally
CASE format
catch NumberFormatException: abc
finally
CASE argument
catch IllegalArgumentException: invalid argument
finally
CASE file
catch FileNotFoundException: config.txt
finally
CASE io
catch IOException: broken stream
finally
```

### Đọc kết quả theo quan hệ kế thừa

| Tình huống | Kiểu đối tượng được ném | Kiểu cha cũng có thể bắt | `catch` thực tế được chọn |
| --- | --- | --- | --- |
| `ok` | Không có ngoại lệ | Không áp dụng | Không có; chạy `after execute` |
| `quantity` | `InvalidQuantityException` | `IllegalArgumentException`, `RuntimeException`, `Exception` | `InvalidQuantityException` |
| `format` | `NumberFormatException` | `IllegalArgumentException`, `RuntimeException`, `Exception` | `NumberFormatException` |
| `argument` | `IllegalArgumentException` | `RuntimeException`, `Exception` | `IllegalArgumentException` |
| `file` | `FileNotFoundException` | `IOException`, `Exception` | `FileNotFoundException` |
| `io` | `IOException` | `Exception`, `Throwable` | `IOException` |

Lưu ý quan trọng:

1. Với `quantity`, `InvalidQuantityException` kế thừa `IllegalArgumentException`; nếu bỏ nhánh `catch (InvalidQuantityException)` thì nhánh `catch (IllegalArgumentException)` sẽ xử lý lỗi đó.
2. Với `format`, `NumberFormatException` cũng kế thừa `IllegalArgumentException`, nhưng được xử lý riêng vì handler con đứng trước.
3. Với `file`, `FileNotFoundException` là `IOException` đặc biệt. Handler riêng có thể hiển thị thông báo “không tìm thấy tệp”; handler `IOException` phía sau dành cho lỗi I/O khác.
4. Với `io`, handler `FileNotFoundException` **không thể** bắt một đối tượng `IOException` thông thường chỉ vì chúng thuộc cùng cây kế thừa.
5. `finally` chạy sau mọi tình huống trong chương trình này. Khi có ngoại lệ, dòng `after execute` không chạy vì lời gọi `execute` không hoàn tất bình thường.

Chương trình chủ động `throw` các ngoại lệ để đầu ra không phụ thuộc tệp thật, hệ điều hành hay định dạng thông điệp nội bộ của JDK.

## 5. Thứ tự tìm handler: vùng `try` trong cùng trước, rồi đến caller

Phân cấp kiểu chỉ là một nửa quy tắc. JVM trước hết xem **handler đang có hiệu lực tại điểm ném**. Nếu có `try-catch` lồng nhau, một handler rộng trong khối bên trong có thể xử lý lỗi **trước khi** handler cụ thể trong khối bên ngoài nhìn thấy nó.

Ví dụ minh họa, đặt trong thân phương thức:

```java
try {
    try {
        throw new NumberFormatException("x");
    } catch (IllegalArgumentException ex) {
        System.out.println("inner: IllegalArgumentException");
    }
} catch (NumberFormatException ex) {
    System.out.println("outer: NumberFormatException");
}
```

Output:

```text
inner: IllegalArgumentException
```

Mặc dù `catch` ngoài là kiểu cụ thể hơn, ngoại lệ đã được **handler bên trong** bắt và không ném tiếp. JVM không bỏ qua handler trong để tìm một handler kiểu con ở tầng ngoài. Điều này cũng có nghĩa một `catch (Exception)` quá rộng trong tầng dưới có thể che mất cơ hội xử lý chuyên biệt ở caller.

Đổi khối `catch` bên trong thành `catch (IllegalArgumentException ex) { throw ex; }` thì ngoại lệ tiếp tục lan ra ngoài. Khi đó, handler `NumberFormatException` của khối ngoài có thể bắt lại đối tượng gốc. Trong trường hợp này không tạo đối tượng ngoại lệ mới; `throw ex` là thao tác ném lại.

### Nhìn từ call stack

```text
main()
  └─ controller()
       └─ service()
            └─ repository()
                 └─ throw FileNotFoundException
                      ↓
            service(): không có catch
                      ↓
       controller(): catch(IOException)
                      ↓
                 xử lý và dừng lan truyền
```

Handler `IOException` ở controller có thể bắt `FileNotFoundException` vì quan hệ cha/con. Nếu service đã bắt bằng `catch (Exception)` và không ném lại, controller không nhận được ngoại lệ, dù controller có handler cho `FileNotFoundException`.

## 6. Khác biệt giữa bắt `Exception`, `RuntimeException` và `Throwable`

Các nhánh sau có độ phủ rất khác nhau:

| Handler | Có thể bắt | Không bắt |
| --- | --- | --- |
| `catch (NumberFormatException ex)` | `NumberFormatException` và lớp con của nó nếu có | `IllegalArgumentException` thông thường, `IOException` |
| `catch (IllegalArgumentException ex)` | `IllegalArgumentException` và lớp con, gồm `NumberFormatException` | `IOException`, `IllegalStateException` |
| `catch (RuntimeException ex)` | Các ngoại lệ thuộc `RuntimeException` | `IOException` và các checked exception khác; `Error` |
| `catch (IOException ex)` | `IOException` và lớp con như `FileNotFoundException` | `RuntimeException`, `Error` |
| `catch (Exception ex)` | Checked exception thuộc `Exception` cùng các `RuntimeException` | Các loại `Error` |
| `catch (Throwable ex)` | `Exception` lẫn `Error` và mọi subclass của `Throwable` | Không có đối tượng `Throwable` nào ở ngoài phạm vi kiểu này |

**Không nên mặc định bắt `Throwable`** ở luồng xử lý nghiệp vụ. Nó có thể bắt cả `OutOfMemoryError` và `LinkageError`, những tình trạng mà ứng dụng có thể không đủ điều kiện tiếp tục an toàn. `catch (Exception)` đôi khi có ích ở ranh giới tác vụ để ghi nhận lỗi, nhưng ở tầng thấp thường quá rộng, có nguy cơ che mất lỗi lập trình.

Cũng cần phân biệt:

- `catch (RuntimeException)` **không** bắt `IOException` chỉ vì ngoại lệ cùng được ném bằng `throw`.
- `catch (Exception)` **có** bắt `NullPointerException` vì `NullPointerException` là hậu duệ của `RuntimeException` → `Exception`.
- `catch (Exception)` **không** bắt `OutOfMemoryError`; `Error` không kế thừa `Exception`.
- Những ngoại lệ runtime do lỗi lập trình có thể lan truyền mà không cần khai báo `throws`, nhưng điều đó không làm chúng mất đi quan hệ kế thừa.

## 7. Multi-catch: bắt nhiều kiểu anh em bằng một handler

Từ Java 7, có thể sử dụng dấu `|` khi nhiều ngoại lệ cần cùng cách xử lý:

```java
try {
    // Thao tác có thể ném IOException hoặc NumberFormatException.
} catch (java.io.IOException | NumberFormatException ex) {
    System.out.println("Không hoàn thành thao tác: "
            + ex.getClass().getSimpleName());
}
```

Đây là cấu trúc minh họa; phần `try` cần có lời gọi phù hợp. Các nhánh trong multi-catch phải **không có quan hệ cha/con với nhau**, để tránh một kiểu bị kiểu còn lại che phủ:

```java
// Sai — cố ý không biên dịch:
catch (NumberFormatException | IllegalArgumentException ex) {
    // NumberFormatException đã là IllegalArgumentException.
}
```

Lý do tương tự khi viết:

```java
// Sai — cố ý không biên dịch:
catch (java.io.IOException | java.io.FileNotFoundException ex) {
    // FileNotFoundException đã là IOException.
}
```

Trong một multi-catch, biến `ex` **ngầm là final**, không được gán sang một ngoại lệ khác. Kiểu tĩnh dùng cho các thao tác trên `ex` được suy ra từ các kiểu lựa chọn và quan hệ kiểu phù hợp; vì vậy không nên giả định có thể gọi phương thức riêng của chỉ một nhánh mà không kiểm tra kiểu.

Multi-catch phù hợp khi nhiều nguyên nhân có **cùng phản ứng thực sự**. Nếu lỗi nhập số cần yêu cầu người dùng sửa còn lỗi tệp cần báo lỗi vận hành, nên dùng các handler riêng.

## 8. Checked và unchecked ảnh hưởng gì tới `catch`?

Phân cấp kế thừa và quy tắc kiểm tra ngoại lệ lúc biên dịch có liên quan nhưng không giống nhau.

### Checked exception

Ví dụ `IOException` và `FileNotFoundException` là checked exceptions. Nếu một phương thức gọi API có thể ném `IOException`, nó phải bắt hoặc khai báo kiểu phù hợp:

```java
static String load(java.nio.file.Path path)
        throws java.io.IOException {
    return java.nio.file.Files.readString(path);
}
```

Phương thức minh họa này không độc lập; đoạn code không phụ thuộc sự hiện diện của một tệp cụ thể. Người gọi có thể:

```java
try {
    String text = load(path);
    // Dùng text khi đọc thành công.
} catch (java.io.IOException ex) {
    // Xử lý lỗi I/O và cả các lớp con được ném từ load.
}
```

Đoạn gọi này cần nằm trong phạm vi có biến `path` kiểu `java.nio.file.Path`. `catch (IOException)` là đủ cho `FileNotFoundException` và các lớp con của `IOException`. Không cần `catch` từng lớp con chỉ để thỏa yêu cầu trình biên dịch.

### Unchecked exception

`NumberFormatException`, `IllegalArgumentException`, `IllegalStateException` là unchecked exceptions. Một lời gọi có thể ném chúng mà phương thức gọi không bắt hoặc khai báo. **Nếu bạn muốn xử lý riêng, quy tắc quan hệ cha/con khi chọn handler vẫn áp dụng y hệt.**

Một thiết kế API không nhất thiết tốt hơn khi mọi lỗi đều chuyển thành `RuntimeException`. Quyết định checked/unchecked cần dựa vào hợp đồng API, khả năng phục hồi và cách các tầng sử dụng lỗi, chứ không chỉ để giảm số chữ `throws`.

### Về việc bắt rồi ném lại

Một `catch` có thể ném lại cùng đối tượng bằng `throw ex;` hoặc bọc vào loại ngoại lệ phù hợp. Đối với checked exceptions, chữ ký phương thức vẫn phải thỏa quy tắc của trình biên dịch. Trong một số trường hợp Java phân tích kiểu chính xác khi ném lại biến `catch` không bị gán lại (*precise rethrow*), nhưng không nên dựa vào nhận định rằng mọi `catch (Exception ex) { throw ex; }` đều có thể khai báo tùy ý một kiểu checked hẹp.

## 9. Tạo ngoại lệ riêng: chọn kiểu cha phù hợp

Khi ứng dụng có một loại lỗi riêng mà người gọi cần phân biệt, có thể tạo ngoại lệ kế thừa một lớp có sẵn:

```java
public class InvalidOrderException extends IllegalArgumentException {
    public InvalidOrderException(String message) {
        super(message);
    }

    public InvalidOrderException(String message, Throwable cause) {
        super(message, cause);
    }
}
```

Đây là **một lớp độc lập** nếu lưu dưới tên `InvalidOrderException.java`; để dùng trong chương trình khác, cần đặt cùng package hoặc import thích hợp. Việc kế thừa `IllegalArgumentException` có ý nghĩa nếu lỗi cho biết đối số của lời gọi không hợp lệ. Một lỗi trạng thái nội bộ (ví dụ thao tác gửi khi đơn chưa được khởi tạo) có thể phù hợp hơn với `IllegalStateException`; lỗi I/O có thể phù hợp với `IOException` hoặc subclass của nó.

Các quyết định thiết kế:

1. **Chọn cha theo ngữ nghĩa:** đừng kế thừa `IllegalArgumentException` chỉ để tránh checked exception, nếu bản chất thất bại là lỗi môi trường bên ngoài.
2. **Giữ nguyên nhân gốc:** constructor nhận `Throwable cause` giúp bảo toàn nguyên nhân khi đổi loại ngoại lệ. Không thêm constructor chỉ vì thói quen nếu ứng dụng không dùng.
3. **Tận dụng đa hình:** handler `catch (IllegalArgumentException)` tự động bắt `InvalidOrderException`. Nếu cần xử lý riêng, đặt `catch (InvalidOrderException)` trước.
4. **Tránh phân cấp quá sâu:** nếu nhiều loại lỗi chỉ khác chuỗi thông điệp nhưng xử lý giống nhau, một loại ngoại lệ rõ ràng có thể đủ.
5. **Tài liệu hóa hợp đồng:** ghi các trường hợp ném ngoại lệ bằng `@throws` trong JavaDoc, đặc biệt khi caller phải biết nhánh nào cần phục hồi.

Không thể cho một lớp Java `extends` đồng thời hai lớp ngoại lệ. Nếu cần mô tả nhiều đặc điểm của lỗi, cân nhắc dữ liệu/thuộc tính của ngoại lệ, nguyên nhân gốc hoặc kiểu kết quả có cấu trúc, thay vì một cây kế thừa khó hiểu.

## 10. Chọn handler theo hành động cần làm

Bắt loại cụ thể nhất có ích khi mỗi loại dẫn đến **hành động khác nhau**, không chỉ để in tên lớp:

```java
try {
    // Lời gọi xử lý đầu vào và truy cập dữ liệu.
} catch (NumberFormatException ex) {
    // Thông báo định dạng số sai: người dùng cần sửa đầu vào.
} catch (IllegalArgumentException ex) {
    // Phản hồi tham số không hợp lệ theo hợp đồng ứng dụng.
} catch (java.io.FileNotFoundException ex) {
    // Xử lý hoặc báo thiếu tài nguyên cụ thể.
} catch (java.io.IOException ex) {
    // Báo lỗi I/O hoặc thử lại nếu chính sách cho phép.
}
```

Đây là cấu trúc minh họa; đoạn `try` cần chứa thao tác thực tế có thể ném những kiểu đã liệt kê. Không phải mọi API đều cần bốn nhánh như trên. Nếu phương thức chỉ có thể ném một loại lỗi và mọi người gọi phản ứng như nhau, việc thêm nhiều `catch` không đem lại lợi ích.

Các nguyên tắc giúp tránh bắt sai:

- **Giữ vùng `try` vừa đủ:** nếu gộp cả parse dữ liệu và xử lý nghiệp vụ vào một `try` rộng, `catch (IllegalArgumentException)` có thể vô tình bắt ngoại lệ do một lỗi lập trình ở bước khác.
- **Đừng bắt rồi bỏ qua:** `catch (Exception ignored) {}` che giấu lỗi và làm caller tưởng thao tác thành công.
- **Đừng bắt chỉ để ném y nguyên mà không thêm giá trị:** một `catch` chỉ có `throw ex;` thường là thừa, trừ khi cần một hành động như dọn dẹp hoặc ghi nhận có chủ đích.
- **Chỉ bọc lỗi khi có lý do:** chuyển `IOException` thành `IllegalStateException` có thể hợp lý ở một API không cho phép phục hồi I/O; khi bọc, truyền `cause` để không mất dấu.
- **Đừng xử lý theo chuỗi thông điệp:** không phân nhánh bằng `ex.getMessage().contains("file")`; thông điệp có thể thay đổi, được bản địa hóa hoặc chứa dữ liệu phụ.
- **Cân nhắc hợp đồng của tầng ngoài:** API có thể chuyển lỗi cụ thể thành mã HTTP phù hợp; tầng lưu trữ có thể giữ lại `IOException` cho tầng ứng dụng quyết định. Đây là quyết định thiết kế, không có một loại `catch` đúng cho mọi hệ thống.

## 11. Những lỗi biên dịch và lỗi tư duy thường gặp

| Sai lầm | Tại sao sai | Cách sửa |
| --- | --- | --- |
| Đặt `catch (Exception)` trước `catch (IOException)` | Handler con bị che khuất | Đưa `IOException` lên trước hoặc bỏ handler dư |
| Viết `catch (IOException | FileNotFoundException)` | Hai lựa chọn có quan hệ cha/con | Dùng `catch (IOException)` hoặc tách nhánh riêng |
| Giả định `catch (IOException)` bắt `IllegalStateException` | Hai loại ở nhánh khác nhau | Chọn kiểu theo ngoại lệ thực tế và chính sách xử lý |
| Nghĩ `catch (Exception)` bắt cả `Error` | `Error` là nhánh anh em của `Exception` | Không xem `Error` là lỗi nghiệp vụ thông thường |
| Tin rằng `catch` ngoài “cụ thể hơn” sẽ được ưu tiên | `try-catch` trong có thể xử lý trước | Xác định vùng xử lý đang hoạt động gần điểm ném |
| Gộp mọi lỗi vào `catch (Throwable)` rồi trả thành công | Che lấp lỗi nghiêm trọng và tạo trạng thái sai | Bắt các ngoại lệ có hành động xử lý có ý nghĩa |
| Xác định lỗi bằng `getMessage()` | Thông điệp không phải hợp đồng phân loại kiểu | Dùng kiểu ngoại lệ, thuộc tính hoặc kết quả tường minh |
| Tạo nhiều subclass nhưng không có xử lý phân biệt | API phức tạp mà ít lợi ích | Duy trì phân cấp tối giản dựa theo ngữ nghĩa |

## 12. Bài tập tự kiểm tra

**Tình huống A:** Một phương thức ném `NumberFormatException`. Trong cùng `try` chỉ có `catch (RuntimeException)`. Có bắt được không?

**Có.** `NumberFormatException` là con của `IllegalArgumentException`, mà `IllegalArgumentException` là con của `RuntimeException`.

**Tình huống B:** Có `catch (IOException)` rồi `catch (FileNotFoundException)`. Có biên dịch không?

**Không.** `FileNotFoundException` là subclass của `IOException` và đã được nhánh trước bắt hết.

**Tình huống C:** Một `try` bên trong bắt `IllegalArgumentException` rồi xử lý xong `NumberFormatException` mà không ném lại. `catch (NumberFormatException)` ở `try` ngoài có chạy không?

**Không.** Ngoại lệ đã được xử lý tại phạm vi trong, nên không lan ra ngoài.

**Tình huống D:** Có `catch (Exception)` thì một `OutOfMemoryError` có bị bắt không?

**Không.** `OutOfMemoryError` kế thừa `Error`, còn `Error` không kế thừa `Exception`.

**Tình huống E:** Muốn chung một thông báo cho lỗi đọc tệp và nhập số, có thể viết `catch (IOException | NumberFormatException)` không?

**Có**, nếu cả hai có thể phát sinh trong `try` đang xét. Chúng không có quan hệ cha/con và multi-catch cho phép chung một handler.

**Tình huống F:** Tạo `InvalidOrderException extends IllegalArgumentException`. Nếu xóa handler dành riêng cho `InvalidOrderException`, handler `IllegalArgumentException` phía sau có bắt được không?

**Có.** Handler cha bắt được đối tượng con, miễn là ngoại lệ thực sự truyền đến nó mà chưa được xử lý ở `try` bên trong.

**Ghi nhớ:** Java chọn `catch` bằng **kiểu runtime và quan hệ kế thừa**, đồng thời tuân theo **phạm vi handler đang hoạt động và thứ tự các nhánh trong cùng một `try`**. Hãy đặt handler cụ thể trước handler cha và chỉ bắt ở tầng có hành động xử lý phù hợp.