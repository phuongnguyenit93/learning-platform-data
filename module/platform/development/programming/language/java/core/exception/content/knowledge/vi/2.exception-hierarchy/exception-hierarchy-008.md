# Vì sao `catch (Exception)` không bắt mọi `Throwable` trong Java?

> **Chủ đề:** Java Core — Exception · Phân cấp ngoại lệ. Cốt lõi của câu trả lời: **`Exception` chỉ là một nhánh con của `Throwable`.** `catch (Exception e)` xử lý các đối tượng có kiểu `Exception` hoặc lớp con, còn những đối tượng thuộc nhánh `Error` (và lớp con trực tiếp khác của `Throwable`) không phải là `Exception` nên không khớp. Việc Java cho phép `catch (Throwable)` không có nghĩa ứng dụng nên bắt mọi lỗi ở cấp đó.

## 1. Nhìn đúng cây kế thừa

`Throwable` là lớp gốc của các đối tượng có thể được ném qua `throw` và được bắt bằng `catch` theo hệ thống ngoại lệ Java. Hai nhánh quen thuộc bên dưới nó là `Exception` và `Error`:

```text
java.lang.Object
└── java.lang.Throwable
    ├── java.lang.Exception
    │   ├── java.io.IOException
    │   │   └── java.io.FileNotFoundException
    │   └── java.lang.RuntimeException
    │       ├── java.lang.IllegalArgumentException
    │       │   └── java.lang.NumberFormatException
    │       ├── java.lang.NullPointerException
    │       └── java.lang.IllegalStateException
    │
    ├── java.lang.Error
    │   ├── java.lang.AssertionError
    │   ├── java.lang.LinkageError
    │   └── java.lang.VirtualMachineError
    │       ├── java.lang.OutOfMemoryError
    │       └── java.lang.StackOverflowError
    │
    └── (các lớp khác nếu tự extends Throwable)
```

Cây trên liệt kê **các ví dụ tiêu biểu**, không phải toàn bộ lớp con trong JDK. Sự phân nhánh có nghĩa:

- `Exception extends Throwable`: mọi đối tượng `Exception` đều là `Throwable`.
- `RuntimeException extends Exception`: mọi `RuntimeException` đều là `Exception` và `Throwable`.
- `Error extends Throwable`: mọi đối tượng `Error` đều là `Throwable`, **nhưng không thuộc kiểu `Exception`**.
- Java cho phép viết một lớp trực tiếp `extends Throwable`. Lớp đó cũng không tự trở thành `Exception` hay `Error`. Đây là khả năng của ngôn ngữ, tuy nhiên thường nên chọn một nhánh chuẩn khi thiết kế API.

**Quan hệ quyết định:** `Exception` và `Error` là hai nhánh anh em, không phải quan hệ cha–con. `catch (Exception)` không có nhiệm vụ “bắt tất cả thứ có thể ném”; nó chỉ bắt những đối tượng tương thích với kiểu `Exception`.

## 2. Java chọn một `catch` bằng cách nào?

Khi một exception hoặc error được ném bên trong `try`, runtime kiểm tra các `catch` kèm theo khối đó theo thứ tự khai báo để tìm handler có kiểu tương thích với **đối tượng thực tế đang được ném**.

Một handler `catch (T e)` có thể xử lý đối tượng có kiểu runtime `T` hoặc một lớp con của `T`. Trong thực tế còn có multi-catch như `catch (IOException | IllegalArgumentException e)`, khi đối tượng khớp một trong các kiểu được liệt kê.

Giả sử đối tượng đang được ném là `NumberFormatException`:

- `catch (NumberFormatException e)` khớp chính xác.
- `catch (IllegalArgumentException e)` khớp vì `NumberFormatException` là lớp con của `IllegalArgumentException`.
- `catch (RuntimeException e)` khớp vì đây là một ancestor của nó.
- `catch (Exception e)` khớp vì `RuntimeException extends Exception`.
- `catch (Throwable e)` cũng khớp vì `Throwable` là tổ tiên chung.
- `catch (Error e)` **không khớp**.

Nếu đối tượng là `AssertionError`:

- `catch (AssertionError e)` khớp.
- `catch (Error e)` khớp.
- `catch (Throwable e)` khớp.
- `catch (Exception e)` **không khớp**, vì `AssertionError` nằm dưới `Error`.

### 2.1. Bảng đối chiếu nhanh

| Đối tượng được ném | `catch (Exception)` | `catch (RuntimeException)` | `catch (Error)` | `catch (Throwable)` |
| --- | --- | --- | --- | --- |
| `new IOException("...")` | Có | Không | Không | Có |
| `new NumberFormatException("...")` | Có | Có | Không | Có |
| `new NullPointerException("...")` | Có | Có | Không | Có |
| `new AssertionError("...")` | **Không** | Không | Có | Có |
| `new LinkageError("...")` | **Không** | Không | Có | Có |
| Đối tượng từ lớp trực tiếp `extends Throwable` | **Không** | Không | Không | Có |

Ở đây “có” nghĩa là **tương thích về kiểu**, không ngụ ý handler đó chắc chắn được chạy trong mọi đoạn code: một handler đứng trước có thể đã bắt đối tượng; hoặc exception có thể nằm ở khối `try` khác. Ngoài ra, Java có quy tắc biên dịch về handler không thể tới được (unreachable catch), nên không phải mọi cách xếp các nhánh trên đều là chương trình hợp lệ.

### 2.2. Thứ tự handler khi nhiều `catch` cùng khớp

Trong **cùng một `try`**, Java xét các `catch` theo thứ tự khai báo và chọn nhánh khớp đầu tiên. Do đó, `catch (NumberFormatException)` phải đứng **trước** `catch (Exception)`: nếu đảo ngược, compiler báo handler kiểu con không thể tới được.

```java
try {
    Integer.parseInt("abc");
} catch (NumberFormatException e) {
    System.out.println("Chuỗi không phải số");
} catch (Exception e) {
    System.out.println("Exception khác");
}
```

Đây là mảnh mã đặt trong phương thức; nó in `Chuỗi không phải số`. Thứ tự handler giải thích **handler nào được chọn trong nhánh Exception**; câu hỏi trọng tâm ở đây là giới hạn kiểu: dù đặt ở đâu, `catch (Exception)` vẫn không khớp với `Error` vì `Error` không kế thừa `Exception`.

## 3. Chương trình Java 17: `catch (Exception)` bị `AssertionError` đi qua

Đây là ví dụ độc lập, minh họa hai tình huống bằng cách tách handler ở tầng trong và ngoài. Để quan sát an toàn, dùng `AssertionError` do chương trình **chủ động ném**. Không tạo `OutOfMemoryError`/`StackOverflowError` thực để thử nghiệm.

Lưu thành `CatchExceptionBoundaryDemo.java`:

```java
public class CatchExceptionBoundaryDemo {
    static void runCase(String label, Runnable operation) {
        try {
            try {
                operation.run();
                System.out.println(label + ": thành công");
            } catch (Exception e) {
                System.out.println(label + ": catch Exception -> "
                        + e.getClass().getSimpleName());
            }
        } catch (AssertionError e) {
            System.out.println(label + ": catch AssertionError bên ngoài -> "
                    + e.getClass().getSimpleName());
        } finally {
            System.out.println(label + ": finally");
        }
    }

    public static void main(String[] args) {
        runCase("Parse", () -> {
            Integer.parseInt("abc");
        });

        runCase("Kiểm tra", () -> {
            throw new AssertionError("Chủ động tạo để minh họa");
        });
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 CatchExceptionBoundaryDemo.java
java CatchExceptionBoundaryDemo
```

**Stdout chính xác:**

```text
Parse: catch Exception -> NumberFormatException
Parse: finally
Kiểm tra: catch AssertionError bên ngoài -> AssertionError
Kiểm tra: finally
```

**Giải thích từng đường đi:**

1. `Integer.parseInt("abc")` ném `NumberFormatException`, là lớp con của `RuntimeException` → `Exception`. Handler `catch (Exception)` ở khối trong nhận được nó, nên không cần tìm handler ngoài. Sau đó chạy `finally`.
2. `throw new AssertionError(...)` ném đối tượng thuộc nhánh `Error`. Handler `catch (Exception)` không tương thích, nên exception lan ra khỏi khối trong và được handler `catch (AssertionError)` ở khối ngoài bắt. `finally` của khối ngoài vẫn chạy theo đường điều khiển bình thường của Java.
3. Câu lệnh in `"...: thành công"` không chạy ở cả hai nhánh vì `operation.run()` đều kết thúc bằng ném một `Throwable`.

**Điểm quan trọng:** ví dụ chủ động bắt `AssertionError` **chỉ để chứng minh cơ chế matching**. Nó không khuyến khích ứng dụng bắt lỗi nhánh `Error` như một chính sách phục hồi thông thường.

### 3.1. Điều gì xảy ra nếu không có `catch (AssertionError)` bên ngoài?

Nếu xóa handler ngoài và để `AssertionError` không được xử lý ở tầng cao hơn, lỗi sẽ tiếp tục lan qua các phương thức gọi. Nếu một `Throwable` không được bắt tới ranh giới đầu của thread, handler uncaught exception của thread có thể báo stack trace hoặc xử lý theo cấu hình. Không thể dự đoán mọi dòng in của một stack trace như một stdout ổn định: vị trí line number thay đổi theo file, lỗi thường được báo qua stderr, và handler có thể được cấu hình.

Điều đáng nhớ là **`catch (Exception)` không biến lỗi `Error` thành kết quả hợp lệ**, ngay cả khi trong cùng method có `finally`.

## 4. `Exception` không đồng nghĩa với “checked exception”

Một nhầm lẫn phổ biến khác là nghĩ `catch (Exception)` chỉ bắt checked exception, còn `RuntimeException` là “unchecked nên không bắt được”. Điều này sai.

**Checked/unchecked** là cách Java compiler quản lý nghĩa vụ bắt hoặc khai báo lỗi, khác với việc runtime so kiểu handler:

- `Exception` và các lớp con của nó, **trừ `RuntimeException` và các lớp con**, thường là checked exceptions.
- `RuntimeException` và các lớp con là unchecked, nhưng **vẫn nằm trong nhánh `Exception`**, nên `catch (Exception)` bắt được.
- `Error` và các lớp con là unchecked, nhưng **không nằm trong nhánh `Exception`**, nên `catch (Exception)` không bắt được.
- Một lớp tự tạo `extends Throwable` trực tiếp (ngoài `RuntimeException` và `Error`) thuộc loại checked theo quy tắc của ngôn ngữ, nhưng `catch (Exception)` vẫn không bắt được.

Nói chính xác hơn, một lớp exception là **unchecked** nếu nó là lớp con của `RuntimeException` hoặc `Error`; các lớp throwable còn lại là **checked**. Do đó “checked” không phải tên gọi của toàn bộ và chỉ riêng nhánh `Exception`.

### 4.1. Ví dụ phân loại có thể chạy

Tạo `ThrowableTypeDemo.java`:

```java
import java.io.IOException;

public class ThrowableTypeDemo {
    static final class CustomSignal extends Throwable {
        CustomSignal(String message) {
            super(message);
        }
    }

    static void describe(Throwable value) {
        System.out.println(value.getClass().getSimpleName()
                + " | Exception=" + (value instanceof Exception)
                + " | Error=" + (value instanceof Error));
    }

    public static void main(String[] args) {
        describe(new IOException("I/O"));
        describe(new NumberFormatException("parse"));
        describe(new AssertionError("assert"));
        describe(new CustomSignal("direct Throwable child"));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 ThrowableTypeDemo.java
java ThrowableTypeDemo
```

Stdout:

```text
IOException | Exception=true | Error=false
NumberFormatException | Exception=true | Error=false
AssertionError | Exception=false | Error=true
CustomSignal | Exception=false | Error=false
```

Phương thức `describe(Throwable value)` nhận được tất cả đối tượng vì tham số kiểu `Throwable`. Tuy nhiên truyền đối tượng vào tham số **khác** với dùng `catch`: trong ví dụ này, chương trình chỉ kiểm tra kiểu bằng `instanceof`, không hề ném chúng.

Lớp `CustomSignal extends Throwable` được đưa vào để chứng minh cây kế thừa có thể có các nhánh khác. Vì nó không thuộc `RuntimeException` hay `Error`, nếu method thực sự `throw new CustomSignal(...)` thì compiler sẽ yêu cầu bắt hoặc khai báo kiểu này. Trong thiết kế Java thông thường, nên kế thừa `Exception` hoặc `RuntimeException` tùy hợp đồng thay vì trực tiếp từ `Throwable`.

## 5. Vì sao lại có hai nhánh `Exception` và `Error`?

Sự tách biệt giúp biểu đạt **loại tình huống mà code ứng dụng thường có thể xử lý** so với vấn đề có thể nằm ở cơ chế thực thi, liên kết lớp, máy ảo hoặc lỗi giả định chương trình.

### 5.1. Nhánh `Exception`

Ví dụ:

- `IOException`: đọc/ghi dữ liệu thất bại, file không mở được, stream gặp lỗi.
- `FileNotFoundException`: trường hợp cụ thể dưới `IOException`.
- `NumberFormatException`: chuỗi không thể chuyển thành số yêu cầu.
- `IllegalArgumentException`: tham số không hợp lệ theo API.
- `IllegalStateException`: trạng thái hiện tại không cho phép thao tác.
- `NullPointerException`: thao tác không hợp lệ với tham chiếu `null`, thường là lỗi lập trình hoặc vi phạm hợp đồng.

Một số có phương án xử lý hợp lý: yêu cầu người dùng nhập lại, chọn file khác, hủy thao tác hiện tại hoặc chuyển thành thông báo lỗi đúng ngữ cảnh. Nhưng không phải mọi đối tượng `Exception` đều “nhẹ” hay chắc chắn phục hồi được. Ví dụ `NullPointerException` nhiều khi chỉ ra bug cần sửa; bắt rồi tiếp tục vô điều kiện có thể làm dữ liệu sai nặng hơn.

### 5.2. Nhánh `Error`

Ví dụ:

- `OutOfMemoryError`: JVM không đủ bộ nhớ cho yêu cầu cấp phát hoặc giới hạn bộ nhớ liên quan.
- `StackOverflowError`: luồng gọi quá sâu làm tràn stack.
- `LinkageError`: có vấn đề trong liên kết/tải/kiểm tra tương thích của lớp.
- `AssertionError`: một assertion thất bại, hoặc code chủ động ném đối tượng này.
- `ThreadDeath`: cũng là một `Error` trong Java, liên quan đến cơ chế dừng thread đã lỗi thời.

Nhiều `Error` phản ánh tình trạng môi trường hoặc giả định nền tảng bị phá vỡ, nơi tiếp tục xử lý bình thường có thể thiếu an toàn. Tuy nhiên **không nên khẳng định mọi `Error` đều không thể bắt được hoặc luôn kết thúc toàn bộ JVM**. Chúng vẫn là đối tượng `Throwable` có thể được handler tương thích bắt ở cấp ngôn ngữ. Một `AssertionError` do test tạo là ví dụ dễ bắt trong môi trường kiểm thử. Vấn đề là **có nên phục hồi hay không**, tùy loại lỗi và ranh giới xử lý.

Java không bảo đảm rằng sau `OutOfMemoryError`, chương trình có đủ tài nguyên để log, tạo exception mới, đóng mọi resource hoặc chạy logic phục hồi phức tạp. Vì vậy không nên viết chương trình dựa trên niềm tin rằng `catch (Throwable)` giúp “không bao giờ crash”.

## 6. So sánh `catch (Exception)`, `catch (Error)` và `catch (Throwable)`

| Handler | Bao phủ về kiểu | Cách dùng điển hình | Rủi ro nếu lạm dụng |
| --- | --- | --- | --- |
| `catch (NumberFormatException e)` | Một loại lỗi parse và lớp con | Ở ranh giới nhập dữ liệu, khi có cách giải thích hoặc yêu cầu nhập lại | Chỉ hợp lý nếu có hướng xử lý cụ thể. |
| `catch (IOException e)` | Lỗi I/O và lớp con | Thêm ngữ cảnh, chọn nguồn khác, báo thất bại thao tác | Nuốt lỗi có thể khiến caller tưởng đã hoàn tất. |
| `catch (Exception e)` | Mọi `Exception` và lớp con, gồm checked và unchecked | Ranh giới ứng dụng có chính sách xử lý đa dạng; đôi lúc adapter chuyển đổi lỗi | Che lỗi lập trình nếu bắt quá rộng rồi im lặng. **Không bắt `Error`.** |
| `catch (RuntimeException e)` | RuntimeException và lớp con | Ranh giới chịu trách nhiệm cách ly một số lỗi không dự kiến | Có thể che bug và làm hỏng trạng thái nghiệp vụ. |
| `catch (Error e)` | `Error` và lớp con | Tình huống rất đặc thù, ví dụ kiểm thử một `AssertionError` chủ động tạo | Cố phục hồi từ lỗi VM/linkage có thể nguy hiểm hoặc bất khả thi. |
| `catch (Throwable t)` | Cả nhánh `Exception`, `Error` và các lớp con khác | Công cụ chẩn đoán/framework cấp rất thấp, với chính sách giữ nguyên và lan truyền lỗi nghiêm trọng | Nuốt lỗi nặng, sai trạng thái, biến hệ thống hỏng thành “thành công”. |

**Quy tắc thực dụng:** bắt loại cụ thể nhất mà tầng hiện tại thực sự biết xử lý. Nếu không thể phục hồi, có thể để exception lan lên, thêm ngữ cảnh khi chuyển tầng và giữ nguyên `cause`. “Bắt rộng” là lựa chọn thiết kế ở ranh giới kiểm soát chặt, không phải mẹo để mọi method an toàn.

### 6.1. Một `catch (Throwable)` có ngăn tất cả lỗi trên thế giới?

Không. Đây là handler rộng nhất về **kiểu đối tượng Java có thể ném**, nhưng nó vẫn có giới hạn:

1. Chỉ bắt `Throwable` được ném trong phạm vi `try` tương ứng và truyền qua luồng điều khiển tới handler đó. Ngoại lệ ở một **thread khác** không tự nhảy tới handler của thread hiện tại.
2. Không bảo đảm xử lý được tiến trình bị hệ điều hành chấm dứt, JVM dừng đột ngột, mất điện hoặc sự cố native làm sập tiến trình.
3. Có thể không đủ bộ nhớ/tài nguyên để thực thi handler một cách đáng tin sau lỗi nghiêm trọng.
4. Không biến side effect đã xảy ra thành thao tác có rollback.
5. Không tự phát hiện lỗi logic chỉ tạo kết quả sai nhưng **không ném** exception.

Đừng diễn giải `catch (Throwable)` như một “lá chắn tuyệt đối”.

### 6.2. Vì sao `catch (Exception)` đôi khi vẫn có mặt trong code production?

Ở biên giới của một request handler, task executor, CLI command hoặc job runner, ứng dụng có thể cần chuyển nhiều loại exception thành lỗi của tác vụ cụ thể. Ví dụ một tác vụ riêng thất bại, hệ thống ghi log và đánh dấu tác vụ thất bại rồi tiếp tục nhận công việc khác. Điều này chỉ hợp lý khi:

- phạm vi bắt và trạng thái cần phục hồi đã rõ;
- failure được báo thành failure, không giả như thành công;
- các tài nguyên của tác vụ được dọn đúng;
- lỗi nghiêm trọng ở nhánh `Error` không bị âm thầm nuốt;
- có chính sách về retry, giám sát và cách ly trạng thái đã hỏng.

Ngay cả ở những nơi đó, handler cụ thể hơn thường giúp quyết định phù hợp hơn so với một `catch (Exception)` chung.

## 7. Từ `throw` và `throws` đến handler: đừng nhầm lúc biên dịch với lúc chạy

Xét ví dụ phương thức:

```java
static void readData() throws java.io.IOException {
    throw new java.io.IOException("Không đọc được");
}
```

Đây là đoạn mã minh họa, không phải chương trình đầy đủ. Vì `IOException` là checked exception, một caller trực tiếp phải bắt hoặc khai báo tiếp. Có thể viết `catch (Exception)` để bắt vì `IOException extends Exception`, nhưng dùng `catch (IOException)` giúp diễn đạt ý định cụ thể.

Trong khi đó:

```java
static void detectInvalidState() {
    throw new AssertionError("Giả định chương trình bị phá vỡ");
}
```

Đoạn minh họa thứ hai ném `AssertionError`, là unchecked `Error`. Nó không buộc ghi `throws AssertionError`. Một caller viết `catch (Exception)` quanh lời gọi **vẫn không thể bắt `AssertionError`**. Quy tắc checked/unchecked của compiler và quan hệ kiểu tại runtime là **hai vấn đề khác nhau**.

### 7.1. Một method khai báo `throws Exception` có thể ném `Error` không?

Có. `throws Exception` là khai báo cho khả năng thoát của exception checked tương ứng; nó không cấm RuntimeException hoặc Error phát sinh khi chạy.

Ngược lại, việc một method khai báo `throws Throwable` không bắt buộc caller dùng `catch (Throwable)`. Caller có thể khai báo `throws Throwable`, hoặc bắt các loại phù hợp theo quy tắc checked exception. Trong thiết kế API thông thường, tránh khai báo quá tổng quát khi có thể mô tả lỗi cụ thể.

### 7.2. Compiler kiểm tra được gì?

Compiler kiểm tra các ràng buộc như handler đã bị che bởi handler trước, checked exception chưa bắt/khai báo, và một số handler checked không thể nhận ngoại lệ được ném từ khối `try`. Nhưng compiler không quyết định rằng một `Error` “sẽ không thể xảy ra” chỉ vì method không khai báo `throws Error`.

Không phải mọi đoạn code có `catch (Error)` đều là lựa chọn thiết kế tốt. Khả năng biên dịch không thay thế được đánh giá khả năng phục hồi.

## 8. Ngoại lệ bị bọc: handler nhìn **đối tượng được ném**, không tự chọn `cause`

Lỗi gốc có thể là `Error` nhưng code tầng ngoài ném một `Exception` mới chứa lỗi đó làm nguyên nhân. Khi ấy `catch (Exception)` bắt **wrapper**, vì đối tượng thực sự được ném chính là một `Exception`. Nó không tự “bắt trực tiếp `Error` bên trong”.

Tạo `WrappedThrowableDemo.java`:

```java
public class WrappedThrowableDemo {
    static void callService() {
        try {
            throw new AssertionError("Gốc");
        } catch (AssertionError original) {
            throw new IllegalStateException("Bọc lỗi để minh họa", original);
        }
    }

    public static void main(String[] args) {
        try {
            callService();
        } catch (Exception e) {
            System.out.println("Bắt được: "
                    + e.getClass().getSimpleName());
            System.out.println("Cause: "
                    + e.getCause().getClass().getSimpleName());
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 WrappedThrowableDemo.java
java WrappedThrowableDemo
```

Stdout:

```text
Bắt được: IllegalStateException
Cause: AssertionError
```

Ví dụ dùng `AssertionError` để minh họa quan hệ wrapper/cause **chứ không phải mẫu xử lý Error nên áp dụng**. Trong ứng dụng thực tế, thường tránh chuyển mọi `Error` thành exception bình thường để tiếp tục chạy. Hợp đồng và chính sách ở tầng đó mới quyết định khi nào bọc một nguyên nhân là hợp lý.

Trường hợp đối xứng: một `Error` có `getCause()` là `IOException` thì `catch (Exception)` **không** bắt được đối tượng `Error` đang bay ra, dù nguyên nhân bên trong là checked exception. Handler so kiểu đối tượng **bên ngoài được ném**, không đào sâu `getCause()` để chọn catch.

## 9. `finally`, try-with-resources và quá trình lan truyền

Khi `catch (Exception)` không phù hợp với một `Error`, các handler ở các mức gọi phía trên vẫn có thể được xem xét. Trong quá trình ra khỏi khối, `finally` thông thường vẫn được thực hiện; try-with-resources cũng gọi `close()` của resource theo quy tắc.

Ví dụ:

```java
try {
    throw new AssertionError("Báo lỗi");
} catch (Exception e) {
    System.out.println("Không chạy");
} finally {
    System.out.println("Dọn dẹp");
}
```

Đây là đoạn mã minh họa trong method. Khi chạy, `catch (Exception)` không được chọn; `finally` in ra “Dọn dẹp”; sau đó `AssertionError` tiếp tục lan ra ngoài nếu chưa có handler ở tầng trên. Vì thế, một khối `finally` được thực hiện **không chứng minh** exception đã được xử lý.

Không nên tuyên bố `finally` chắc chắn chạy trong mọi tình huống; nếu process/JVM bị kết thúc bất thường, không có bảo đảm phổ quát. Không nên `return` hoặc ném lỗi mới trong `finally` vì có thể che lỗi gốc.

### 9.1. Tránh bỏ mất lỗi khi dọn dẹp

Nếu thân try-with-resources ném exception và `close()` cũng ném, Java thường giữ lỗi của thân khối làm exception chính; lỗi đóng được thêm vào `getSuppressed()`. Cơ chế này áp dụng theo quy tắc của try-with-resources, không phụ thuộc giả định “`catch (Exception)` sẽ bắt được mọi lỗi”.

Nếu exception chính là `Error`, handler `catch (Exception)` vẫn không xử lý được nó, dù một lỗi `IOException` từ `close()` đã được suppressed vào đối tượng chính. Nhánh loại lỗi được **ném ra ngoài** mới quyết định handler nào khớp.

## 10. Cần bắt `Error` khi nào?

Không có quy tắc “tuyệt đối không bao giờ bắt `Error`” trong ngôn ngữ Java. Một số môi trường chuyên biệt có thể cần nhận diện một lỗi cụ thể:

- Framework kiểm thử có thể ghi nhận `AssertionError` như test failure để báo cáo.
- Công cụ chẩn đoán hoặc ranh giới runtime rất thấp có thể quan sát lỗi để ghi thông tin tối thiểu rồi **ném tiếp**.
- Mã có giao thức cách ly và phục hồi rất cụ thể có thể xử lý một loại `Error` đặc thù; quyết định này cần hiểu sâu về API và trạng thái của hệ thống.

Nhưng với code nghiệp vụ thông thường, không nên:

```java
// Phản ví dụ: đừng dùng như chiến lược xử lý lỗi chung.
try {
    performBusinessOperation();
} catch (Throwable ignored) {
    // Nuốt mọi Throwable rồi tiếp tục như thể thành công.
}
```

Đoạn trên là **mã minh họa không độc lập**: `performBusinessOperation()` chưa được định nghĩa. Nó cho thấy anti-pattern cần tránh, không phải chương trình Java hoàn chỉnh.

Cách tốt hơn ở ranh giới xử lý ứng dụng thường là bắt đúng exception có kế hoạch phục hồi; dọn dẹp tài nguyên bằng try-with-resources; log hoặc truyền tiếp các thất bại không thể tự khôi phục; để lỗi nghiêm trọng được xử lý bằng chính sách vận hành/thử lại/khởi động lại phù hợp.

Đặc biệt, không cố tạo `OutOfMemoryError` hay `StackOverflowError` trên môi trường đang làm việc chỉ để kiểm tra bảng matching. Dùng `AssertionError` chủ động tạo là đủ để chứng minh quan hệ kế thừa và handler.

## 11. Những nhầm lẫn cần tránh

| Nhận định sai | Giải thích đúng |
| --- | --- |
| “`Throwable` và `Exception` là cùng một kiểu.” | `Exception` là **một lớp con** của `Throwable`; `Error` là nhánh khác. |
| “`catch (Exception)` bắt mọi thứ có thể được `throw`.” | Nó không bắt `Error` hoặc lớp con trực tiếp khác của `Throwable` nằm ngoài `Exception`. |
| “`RuntimeException` là unchecked nên `catch (Exception)` không bắt được.” | `RuntimeException extends Exception`; vẫn bắt được. |
| “`Error` không thể `catch`.” | Có thể bắt bằng kiểu tương thích (`Error`, `Throwable` hoặc lớp con cụ thể), nhưng không nhất thiết nên phục hồi. |
| “`catch (Throwable)` bảo đảm app không bao giờ dừng.” | Nó không bảo vệ khỏi dừng JVM/process, lỗi native, thiếu tài nguyên nghiêm trọng hay exception ở thread khác. |
| “Checked exception nghĩa là kế thừa trực tiếp `Exception`.” | Checked/unchecked tuân theo nhánh `RuntimeException`/`Error`; một lớp trực tiếp `extends Throwable` có thể là checked. |
| “`throws Exception` ngăn method ném `Error`.” | `throws` không áp đặt giới hạn đó lên unchecked `Error`. |
| “Một `Error` nằm trong `getCause()` sẽ làm `catch (Exception)` thất bại.” | Handler so với **wrapper đang được ném**; nếu wrapper là `Exception` thì catch vẫn khớp. |
| “Nếu `finally` chạy thì exception đã được bắt.” | `finally` thường chạy cả khi exception đang lan truyền; không phải handler. |
| “Bắt rộng rồi bỏ qua sẽ làm chương trình an toàn.” | Nó có thể che lỗi nghiêm trọng và để trạng thái hỏng tiếp tục được sử dụng. |
| “Handler kiểm tra kiểu ngoại lệ theo biến khai báo ban đầu.” | Handler chọn theo **kiểu thực tế của đối tượng được ném** và quan hệ kế thừa. |

## 12. Bài tập kiểm tra hiểu sâu

### Bài 1 — Dự đoán nhánh bắt mà không chạy chương trình

Với từng đối tượng sau, cho biết `catch (Exception)` có nhận không, rồi giải thích quan hệ kế thừa:

1. `new ArithmeticException("division")`.
2. `new java.io.EOFException("end")`.
3. `new AssertionError("broken invariant")`.
4. `new java.lang.NoClassDefFoundError("missing")`.
5. `new IllegalStateException("state")`.

**Đáp án:** (1) có, (2) có, (3) không, (4) không, (5) có. `ArithmeticException` và `IllegalStateException` là các lớp con của `RuntimeException` → `Exception`; `EOFException` thuộc nhánh `IOException` → `Exception`. `AssertionError` và `NoClassDefFoundError` thuộc nhánh `Error`.

### Bài 2 — Chỉnh thứ tự handler

Cho đoạn minh họa:

```java
try {
    Integer.parseInt("?");
} catch (Exception e) {
    System.out.println("Chung");
} catch (NumberFormatException e) {
    System.out.println("Riêng");
}
```

Tại sao không biên dịch? Hãy sửa bằng cách đảo nhánh cụ thể lên trước. Sau khi sửa, stdout là `Riêng`, bởi đối tượng được ném là `NumberFormatException` và handler đầu tiên tương thích đã nhận nó.

### Bài 3 — Bọc lỗi có thay đổi kết quả matching?

Trong `WrappedThrowableDemo`, thay `new IllegalStateException("...", original)` bằng `new AssertionError("...", original)`. Hỏi `catch (Exception)` ở `main` có nhận lỗi không? Vì sao?

**Gợi ý:** handler không tự mở `cause`. Lỗi được ném ở ngoài bây giờ là `AssertionError` (nhánh `Error`), vì vậy `catch (Exception)` không khớp.

### Bài 4 — Lỗi ở thread khác

Nếu `main` viết `try { new Thread(task).start(); } catch (Exception e) { ... }`, còn `task` ném một exception sau khi thread chạy, handler trong `main` có bắt được ngoại lệ đó không? **Không**, vì ngoại lệ xảy ra trên thread khác; handler của `main` chỉ áp dụng cho luồng điều khiển của thread hiện tại. Hãy tìm hiểu `Thread.UncaughtExceptionHandler` hoặc cơ chế thu lỗi qua `Future` khi học concurrency.

### Bài 5 — Thiết kế chính sách

Với ứng dụng xử lý file do người dùng chọn, quyết định tầng nào sẽ bắt `FileNotFoundException`/`IOException`, tầng nào thông báo cho người dùng, và bạn sẽ làm gì nếu gặp `OutOfMemoryError`. Nêu lý do tại sao không nên dùng `catch (Throwable)` rồi quay về thông báo “Đọc file thành công”.

## 13. Checklist ghi nhớ

- [ ] Vẽ được `Throwable` với hai nhánh tiêu biểu `Exception` và `Error`.
- [ ] Giải thích được `RuntimeException` là unchecked nhưng vẫn thuộc `Exception`.
- [ ] Giải thích được tại sao `AssertionError` không bị `catch (Exception)` bắt.
- [ ] Chạy `CatchExceptionBoundaryDemo.java` và giải thích bốn dòng stdout.
- [ ] Chạy `ThrowableTypeDemo.java` và xác nhận một lớp có thể `extends Throwable` trực tiếp.
- [ ] Phân biệt kiểm tra checked/unchecked lúc biên dịch với matching handler lúc chạy.
- [ ] Nêu được một trường hợp `catch (Throwable)` có thể hợp lý và vì sao nó cần chính sách rất chặt.
- [ ] Đọc được wrapper exception và `getCause()` mà không nhầm kiểu lỗi đang được ném.
- [ ] Hiểu rằng `finally`/try-with-resources hỗ trợ dọn dẹp nhưng không tự xử lý hay rollback lỗi.
- [ ] Luôn ưu tiên bắt kiểu lỗi mình có khả năng xử lý thay vì nuốt `Throwable`.

**Kết luận:** `catch (Exception)` là một handler rộng **bên trong nhánh `Exception`**, không phải handler của mọi `Throwable`. `Error` và các nhánh khác của `Throwable` nằm ngoài phạm vi đó. Sự khác biệt đến từ cây kế thừa và quy tắc matching của Java, còn quyết định có nên bắt lỗi hay không phụ thuộc khả năng phục hồi và hợp đồng xử lý ở từng tầng ứng dụng.