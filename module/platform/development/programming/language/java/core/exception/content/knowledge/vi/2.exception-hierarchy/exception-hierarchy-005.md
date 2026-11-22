# Unchecked exception trong Java: `RuntimeException`, `Error` và các lớp con

Java phân chia các đối tượng có thể ném (`Throwable`) thành hai nhóm theo **quy tắc kiểm tra ngoại lệ của trình biên dịch**: *checked exception* và *unchecked exception*. **Unchecked exception** gồm `RuntimeException`, `Error` và mọi lớp con của hai loại này. Khi gọi một phương thức có thể ném unchecked exception, trình biên dịch Java **không bắt buộc** nơi gọi phải viết `try/catch` hoặc khai báo `throws` cho exception đó.

Từ “unchecked” chỉ nói về **nghĩa vụ khai báo hoặc bắt ngoại lệ tại thời điểm biên dịch**. Nó **không** có nghĩa JVM bỏ qua ngoại lệ, chương trình chắc chắn tiếp tục chạy, ngoại lệ không nghiêm trọng, hay Java không thể phát hiện một số vấn đề từ sớm. Khi một unchecked exception thực sự được ném, nó vẫn sử dụng đầy đủ cơ chế của `Throwable`: ngắt đường thực thi thông thường, đi lên chuỗi lời gọi, được tìm `catch` phù hợp, mang message, cause và stack trace.

Điểm quan trọng nhất của bài: cả hai đều unchecked nhưng **`RuntimeException` thường gắn với thao tác hoặc trạng thái ứng dụng**, còn **`Error` thường biểu diễn vấn đề nghiêm trọng ở môi trường thực thi, liên kết lớp hoặc bất biến nội bộ**. Cách ứng xử thường khác nhau và không thể chỉ dựa vào chữ “unchecked”.

## 1. Unchecked nằm ở đâu trong hệ phân cấp?

Sơ đồ rút gọn, không liệt kê toàn bộ Java API:

```text
java.lang.Throwable
├── java.lang.Error                              ← unchecked
│   ├── VirtualMachineError
│   │   ├── OutOfMemoryError
│   │   └── StackOverflowError
│   ├── LinkageError
│   │   ├── NoClassDefFoundError
│   │   └── ExceptionInInitializerError
│   └── AssertionError
└── java.lang.Exception                          ← checked (bản thân kiểu này)
    ├── IOException                              ← checked
    ├── ReflectiveOperationException             ← checked
    └── RuntimeException                         ← unchecked
        ├── IllegalArgumentException
        │   └── NumberFormatException
        ├── IllegalStateException
        ├── NullPointerException
        ├── IndexOutOfBoundsException
        │   ├── ArrayIndexOutOfBoundsException
        │   └── StringIndexOutOfBoundsException
        ├── ArithmeticException
        ├── ClassCastException
        └── UnsupportedOperationException
```

Các tên ví dụ trong sơ đồ là các lớp Java thực. Một lớp con của `RuntimeException` vẫn thuộc nhánh `Exception` nhưng **không còn là checked exception**. Tương tự, mọi lớp con của `Error` thuộc nhóm unchecked.

Theo quy tắc của ngôn ngữ Java, checked exception là các lớp con của `Throwable` **không** thuộc nhánh `RuntimeException` hoặc nhánh `Error`. Vì vậy `Exception` là một kiểu checked, trong khi `RuntimeException` là unchecked. Nói “mọi `Exception` đều checked” là sai.

| Nhánh | Checked hay unchecked? | Điều trình biên dịch yêu cầu ở nơi gọi | Phản ứng điển hình |
| --- | --- | --- | --- |
| `IOException` | Checked | Bắt hoặc khai báo nếu phương thức có thể ném | Quyết định khôi phục, dùng phương án dự phòng hoặc truyền lỗi |
| `RuntimeException` và các lớp con | Unchecked | Không bắt buộc bắt/khai báo | Kiểm tra tiền điều kiện, trạng thái, dữ liệu; bắt có chọn lọc ở tầng phù hợp |
| `Error` và các lớp con | Unchecked | Không bắt buộc bắt/khai báo | Ưu tiên điều tra/sửa môi trường hoặc chương trình; thường không xử lý như một nhánh nghiệp vụ |
| `Exception` | Checked | Bắt hoặc khai báo nếu một biểu thức có thể ném kiểu này | Không đồng nhất với riêng `RuntimeException` |

**Phân biệt thuật ngữ:** “lỗi biên dịch” là việc `javac` không chấp nhận mã nguồn; “lỗi runtime” là vấn đề khi chạy; còn lớp Java `Error` là **một nhánh cụ thể của `Throwable`**. Không phải mọi lỗi chạy đều là đối tượng `Error`. Một `NullPointerException`, chẳng hạn, là `RuntimeException`.

## 2. Vì sao `RuntimeException` không bị kiểm tra bắt buộc ở compile time?

Nhiều sai sót được phát hiện khi chạy phụ thuộc giá trị hoặc trạng thái mà trình biên dịch không thể biết từ một lời gọi: tham số có phải `null` không, chỉ số mảng có nằm trong giới hạn không, dữ liệu đầu vào có chuyển thành số được không, đối tượng có đang ở trạng thái cho phép hay không.

Ví dụ, lời gọi `Integer.parseInt(text)` hợp lệ về kiểu vì tham số là `String`. Java không thể đảm bảo rằng mỗi giá trị thực tế của `text` biểu diễn số nguyên hợp lệ. API có thể ném `NumberFormatException` (một lớp con của `IllegalArgumentException`, rồi `RuntimeException`), nhưng mọi nơi gọi `parseInt` không bị buộc phải có `catch`.

Tương tự, các phương thức Java rất thường xuyên có thể gặp lỗi như `NullPointerException`; nếu tất cả chúng đều phải khai báo hoặc bắt checked exception, chữ ký và luồng gọi sẽ trở nên rất cồng kềnh mà không làm mã an toàn hơn theo cách tương ứng.

**Không bị kiểm tra bắt buộc khác với không kiểm tra được bằng công cụ.** Compiler, IDE, phân tích tĩnh, test và công cụ kiểm tra `null` có thể phát hiện một phần nguy cơ trước khi chạy; chỉ là quy tắc `catch-or-declare` của Java không áp dụng cho các loại này.

Cũng đừng hiểu “unchecked” đồng nghĩa với bug: một số API chủ động sử dụng `IllegalArgumentException` để báo bên gọi vi phạm hợp đồng; một số ngoại lệ có thể đến từ dữ liệu bên ngoài. Tuy nhiên, nếu cùng tình huống là nhánh nghiệp vụ thường xảy ra, loại kết quả rõ ràng có thể dễ dùng hơn việc ném ngoại lệ.

## 3. Ví dụ kiểm tra chính xác nhánh nào là unchecked

Lưu đoạn mã sau thành `ExceptionHierarchyDemo.java`. Chương trình dùng quan hệ kế thừa kiểu của Java để kiểm tra loại nào thuộc nhánh `RuntimeException` hoặc `Error`.

```java
import java.io.IOException;

public class ExceptionHierarchyDemo {
    static void inspect(Class<? extends Throwable> type) {
        boolean runtime = RuntimeException.class.isAssignableFrom(type);
        boolean error = Error.class.isAssignableFrom(type);
        boolean unchecked = runtime || error;

        System.out.println(type.getSimpleName()
                + " | unchecked=" + unchecked
                + " | runtime=" + runtime
                + " | error=" + error);
    }

    public static void main(String[] args) {
        inspect(IOException.class);
        inspect(Exception.class);
        inspect(NumberFormatException.class);
        inspect(NullPointerException.class);
        inspect(OutOfMemoryError.class);
        inspect(AssertionError.class);
    }
}
```

Biên dịch và chạy với Java 17 trở lên:

```bash
javac --release 17 ExceptionHierarchyDemo.java
java ExceptionHierarchyDemo
```

**stdout chính xác:**

```text
IOException | unchecked=false | runtime=false | error=false
Exception | unchecked=false | runtime=false | error=false
NumberFormatException | unchecked=true | runtime=true | error=false
NullPointerException | unchecked=true | runtime=true | error=false
OutOfMemoryError | unchecked=true | runtime=false | error=true
AssertionError | unchecked=true | runtime=false | error=true
```

`Class.isAssignableFrom` trả về `true` khi đối tượng `Class` ở bên trái đại diện cho kiểu cha hoặc chính kiểu của đối tượng `Class` truyền vào. Vì thế `RuntimeException.class.isAssignableFrom(NumberFormatException.class)` là `true`; quan hệ này được xác định từ phân cấp kế thừa, không phụ thuộc tên lớp hoặc nội dung message.

Ví dụ không tạo hay ném `OutOfMemoryError`: nó chỉ **kiểm tra quan hệ kiểu**, an toàn và có thể dự đoán kết quả.

## 4. Những `RuntimeException` thường gặp

`RuntimeException` biểu diễn nhiều tình huống xảy ra trong khi ứng dụng hoặc thư viện vận hành. Java và thư viện chuẩn cung cấp hàng loạt lớp con cụ thể để thông báo bản chất vấn đề:

| Loại | Tình huống điển hình | Hướng xử lý |
| --- | --- | --- |
| `NullPointerException` | Dereference tham chiếu `null`, gọi method/truy cập field không hợp lệ | Sửa nguyên nhân `null`, làm rõ hợp đồng đầu vào và trạng thái |
| `IllegalArgumentException` | Bên gọi truyền đối số vi phạm hợp đồng | Kiểm tra điều kiện và hợp đồng của API |
| `NumberFormatException` | `Integer.parseInt("abc")` không chuyển được sang số nguyên | Xác thực dữ liệu văn bản, báo lỗi nhập phù hợp |
| `IllegalStateException` | Thao tác được yêu cầu khi đối tượng ở trạng thái không cho phép | Xem luồng trạng thái, thời điểm và trình tự lời gọi |
| `IndexOutOfBoundsException` | Truy cập chỉ số ngoài phạm vi của chuỗi/danh sách | Kiểm tra biên và kích thước dữ liệu |
| `ArrayIndexOutOfBoundsException` | Truy cập vị trí không tồn tại trong mảng | Dùng ranh giới `0 <= i < array.length` |
| `ArithmeticException` | Ví dụ `int x = 10 / 0;` trong số học nguyên | Kiểm tra số chia, xử lý điều kiện đầu vào |
| `ClassCastException` | Ép kiểu tham chiếu đến kiểu không tương thích tại runtime | Thiết kế kiểu đúng và kiểm tra kiểu khi cần |
| `UnsupportedOperationException` | Thao tác không được collection hoặc API cụ thể hỗ trợ | Chọn thao tác/triển khai đáp ứng hợp đồng |

Lưu ý quan trọng:

- `NumberFormatException` **kế thừa** `IllegalArgumentException`; `ArrayIndexOutOfBoundsException` **kế thừa** `IndexOutOfBoundsException`. Thứ tự các nhánh `catch` phải phù hợp quan hệ này.
- `ArithmeticException` không có nghĩa mọi phép toán số học Java đều kiểm tra tất cả sai số: phép chia số nguyên cho `0` ném ngoại lệ, nhưng tràn số nguyên thông thường không tự ném ngoại lệ; chia số thực theo IEEE 754 có hành vi riêng (ví dụ `Infinity` hoặc `NaN`).
- `NullPointerException` có thể do JVM tự phát sinh hoặc do mã chủ động ném (ví dụ dùng `Objects.requireNonNull`). Khả năng nhận diện vị trí và thông điệp tùy cách lỗi phát sinh.
- `UnsupportedOperationException` là unchecked; không phải mọi collection đều hỗ trợ mọi phép sửa đổi. Ví dụ `List.of(1, 2).add(3)` sẽ ném `UnsupportedOperationException`.
- Các exception khác trong hệ Java cũng có thể thuộc nhóm unchecked; danh sách ở đây nhằm nhận diện những trường hợp quan trọng nhất.

### Lỗi do người dùng hay lỗi của lập trình viên?

Một ngoại lệ như `NumberFormatException` có thể phát sinh vì người dùng gõ chữ vào ô số. Tầng giao tiếp có thể bắt lỗi và trả thông báo xác thực **bình thường**. Nhưng nếu chính mã nội bộ chuyển đổi sai một cấu hình đã được kiểm tra, nó có thể là bug hoặc lỗi dữ liệu hệ thống.

Phân loại dựa trên **hợp đồng của thao tác** và nguồn dữ liệu, không chỉ tên exception. Không nên đổi mọi trường hợp “người dùng nhập sai” thành một chuỗi unchecked exception truyền qua cả hệ thống nếu ứng dụng vốn có nhánh xác thực rõ ràng.

## 5. Unchecked exception được ném, lan truyền và bắt thế nào?

Cơ chế lan truyền không khác checked exception. Khi `throw` được thực thi, các câu lệnh tiếp theo trên nhánh thực thi đó bị bỏ qua; JVM tìm `catch` có kiểu tương thích trong khối `try` hiện tại rồi các phương thức gọi phía ngoài.

Vì unchecked exception không bắt buộc `throws`, **không có `throws` không chứng minh phương thức sẽ không thất bại**. Ví dụ:

```java
static int parseQuantity(String text) {
    int quantity = Integer.parseInt(text);
    if (quantity <= 0) {
        throw new IllegalArgumentException("Số lượng phải dương");
    }
    return quantity;
}
```

Đây là đoạn phương thức minh họa, không phải một chương trình độc lập. Hàm không khai báo `throws NumberFormatException` hay `throws IllegalArgumentException` mà vẫn biên dịch hợp lệ; bên gọi vẫn có thể nhận ngoại lệ lúc chạy.

Bạn **có thể** khai báo `throws IllegalArgumentException` để tài liệu hóa hợp đồng:

```java
static int parseQuantity(String text) throws IllegalArgumentException {
    return Integer.parseInt(text);
}
```

Đây cũng chỉ là phương thức minh họa. Khai báo đó **không bắt buộc** phía gọi bắt hoặc khai báo lại. Và `throws` không “bật” khả năng ném exception: các exception unchecked đã có thể xảy ra dù chữ ký không liệt kê chúng.

### Ví dụ chạy đầy đủ với nhiều nhánh

Lưu thành `UncheckedFlowDemo.java`:

```java
public class UncheckedFlowDemo {
    static int parsePositive(String text) {
        int value = Integer.parseInt(text);
        if (value <= 0) {
            throw new IllegalArgumentException("Số lượng phải lớn hơn 0");
        }
        return value;
    }

    static int price(int quantity, boolean available) {
        if (!available) {
            throw new IllegalStateException("Bộ tính giá chưa sẵn sàng");
        }
        return quantity * 20;
    }

    public static void main(String[] args) {
        String[] texts = {"2", "abc", "0", "3"};
        boolean[] available = {true, true, true, false};

        for (int i = 0; i < texts.length; i++) {
            String input = texts[i];

            try {
                int quantity = parsePositive(input);
                System.out.println(input + " -> " + price(quantity, available[i]));
            } catch (NumberFormatException e) {
                System.out.println(input + " -> không phải số nguyên");
            } catch (IllegalArgumentException e) {
                System.out.println(input + " -> " + e.getMessage());
            } catch (IllegalStateException e) {
                System.out.println(input + " -> " + e.getMessage());
            }
        }
        System.out.println("Hoàn tất vòng lặp");
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 --release 17 UncheckedFlowDemo.java
java UncheckedFlowDemo
```

**stdout chính xác** với console hiển thị UTF-8:

```text
2 -> 40
abc -> không phải số nguyên
0 -> Số lượng phải lớn hơn 0
3 -> Bộ tính giá chưa sẵn sàng
Hoàn tất vòng lặp
```

Giải thích: đầu vào `"2"` đi theo đường thành công. `"abc"` khiến `parseInt` ném `NumberFormatException`. `"0"` chuyển đổi số thành công rồi điều kiện do ứng dụng đặt ra ném `IllegalArgumentException`. `"3"` qua bước chuyển đổi nhưng `price` ném `IllegalStateException` do trạng thái không sẵn sàng. Cả ba exception được `catch` phù hợp xử lý; vòng lặp có thể tiếp tục.

Hai nhánh `catch` đầu minh họa nguyên tắc **bắt lớp con trước lớp cha**: `NumberFormatException` là lớp con của `IllegalArgumentException`. Đảo thứ tự hai nhánh sẽ dẫn tới lỗi biên dịch vì nhánh bắt `NumberFormatException` phía sau trở nên không thể tới.

Ví dụ dùng `available` như trạng thái kỹ thuật “bộ tính giá đã khởi tạo”. Một tình huống từ chối nghiệp vụ thường gặp, như **hết hàng**, nên có thể được thiết kế thành kết quả có trạng thái thay vì gộp với lỗi `IllegalStateException`.

## 6. `Error` cũng unchecked, nhưng không phải lỗi nghiệp vụ

`Error` là nhánh con trực tiếp của `Throwable`, **khác nhánh `Exception`**. `Error` và các lớp con là unchecked: compiler không bắt buộc caller viết `catch` hoặc `throws`. Tuy nhiên, khác với nhiều `RuntimeException` dùng để báo tham số hoặc trạng thái sai, `Error` thường gắn với vấn đề nghiêm trọng ở môi trường chạy, nạp lớp hoặc bất biến chương trình.

| Họ `Error` | Ví dụ | Cách hiểu và giới hạn xử lý |
| --- | --- | --- |
| `VirtualMachineError` | `OutOfMemoryError`, `StackOverflowError` | Có thể thiếu bộ nhớ/stack hoặc thuật toán đệ quy sai; bắt được không có nghĩa phục hồi an toàn |
| `LinkageError` | `NoClassDefFoundError`, `ExceptionInInitializerError` | Có thể liên quan dependency, classpath hoặc khởi tạo lớp; cần tìm và sửa nguyên nhân |
| `AssertionError` | Assertion bị vi phạm | Có thể do mã hoặc test chủ động tạo; **không** nhất thiết JVM đã hỏng |

Một `OutOfMemoryError` không chỉ có một nguyên nhân `Java heap space`: thông điệp có thể chỉ heap, metaspace hay giới hạn tài nguyên khác tùy JVM. Với `StackOverflowError`, thường phải sửa độ sâu đệ quy/điều kiện dừng; không được xem bắt lỗi là cách chữa thuật toán. Với `NoClassDefFoundError`, không đồng nhất nó với checked `ClassNotFoundException`.

**Cốt lõi của bài unchecked:** không có yêu cầu bắt/khai báo ở *compile time* không có nghĩa lỗi bị bỏ qua ở *runtime*. Những chi tiết vận hành sâu của `VirtualMachineError` không thay đổi quy tắc phân loại này.

## 7. Bắt `Throwable` có thể nuốt cả `Error`

`catch (Exception)` bao phủ checked exception dưới `Exception` **và** mọi `RuntimeException`, nhưng **không** bắt `Error`. `catch (Throwable)` rộng hơn: nó có thể nhận cả `OutOfMemoryError` và `LinkageError`. Vì vậy, mã nghiệp vụ không nên bắt `Throwable` rồi im lặng trả thành công.

```java
// Phản ví dụ: các hàm minh họa nằm trong ngữ cảnh ứng dụng.
try {
    runTask();
} catch (Throwable ignored) {
    // Rất nguy hiểm: cũng nuốt cả Error.
}
```

Bắt rộng chỉ có thể hợp lý ở ranh giới đặc biệt, ví dụ test runner hoặc hạ tầng chẩn đoán có chính sách ghi nhận, cách ly và ném lại rõ ràng. Khi biết cách xử lý cụ thể, nên bắt **loại lỗi cụ thể**. Không dùng `catch (Throwable)` thay cho dọn dẹp: `try-with-resources` hoặc `finally` phù hợp hơn để bảo toàn vòng đời tài nguyên trong luồng thực thi Java thông thường.

## 8. Tự tạo unchecked exception khi hợp đồng thực sự cần

Trong một số API, một điều kiện bất thường có ý nghĩa riêng và bên gọi cần bắt chính xác theo loại. Có thể tạo lớp con của `RuntimeException`:

```java
public class CustomUncheckedDemo {
    static class InvalidTransitionException extends RuntimeException {
        InvalidTransitionException(String message) {
            super(message);
        }
    }

    enum State {
        CREATED, SHIPPED
    }

    static void ship(State state) {
        if (state != State.CREATED) {
            throw new InvalidTransitionException(
                    "Chỉ được gửi đơn ở trạng thái CREATED");
        }
        System.out.println("Đã gửi đơn");
    }

    public static void main(String[] args) {
        ship(State.CREATED);
        try {
            ship(State.SHIPPED);
        } catch (InvalidTransitionException e) {
            System.out.println(e.getMessage());
        }
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 --release 17 CustomUncheckedDemo.java
java CustomUncheckedDemo
```

**stdout chính xác** với UTF-8:

```text
Đã gửi đơn
Chỉ được gửi đơn ở trạng thái CREATED
```

`InvalidTransitionException` kế thừa `RuntimeException` nên cũng unchecked; `ship` không cần khai báo `throws`. Bên gọi vẫn có thể bắt đúng loại để xử lý.

Tuy nhiên, không nhất thiết phải dùng exception cho mọi trạng thái đơn hàng. Nếu “không thể gửi vì đơn đã được gửi” là trường hợp thông thường mà hệ thống cần thông báo cho người dùng, trả về kiểu kết quả như `ALREADY_SHIPPED` có thể rõ ràng hơn. Custom exception thích hợp hơn khi thao tác bị gọi trái tiền điều kiện/bất biến của API và cần dừng luồng hiện tại.

Không tự tạo lớp con của `Error` để biểu diễn lỗi validation, hết hàng hay giao dịch bị từ chối. Điều đó khiến người đọc hiểu sai mức độ nghiêm trọng và bỏ qua các ranh giới xử lý `Exception` bình thường.

Khi cần tạo exception từ nguyên nhân khác, nên có constructor cho message và cause:

```java
// Minh họa định nghĩa kiểu, không chứa main.
class ConfigurationRuntimeException extends RuntimeException {
    ConfigurationRuntimeException(String message, Throwable cause) {
        super(message, cause);
    }
}
```

Giữ `cause` giúp chẩn đoán lỗi gốc. Chỉ chuyển checked thành unchecked khi hợp đồng của lớp hiện tại cho phép và tầng gọi biết cách ứng phó; tránh bọc lại chỉ để lách quy tắc checked exception.

## 9. Checked và unchecked khác nhau ở đâu trong mã nguồn?

Xét hai phương thức minh họa:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

class FileAndInput {
    static String load(Path path) throws IOException {
        return Files.readString(path);
    }

    static int parse(String text) {
        return Integer.parseInt(text);
    }
}
```

Mã này là lớp Java hợp lệ, nhưng không có phương thức `main`. `load` có thể ném `IOException` nên khai báo `throws IOException`; bên gọi không ở trong ngữ cảnh `catch` phù hợp hoặc không `throws` tiếp sẽ gặp lỗi biên dịch khi gọi. `parse` có thể ném `NumberFormatException` nhưng không bắt buộc khai báo và bên gọi không bị buộc phải bắt.

Hai điều thường bị hiểu sai:

1. Nếu `parse` tự ý thêm `throws NumberFormatException` vào chữ ký, **kiểu vẫn unchecked**; nghĩa vụ compile time ở caller không đổi.
2. Nếu một phương thức khai báo `throws Exception`, bên gọi phải xét nghĩa vụ bắt/khai báo **kiểu checked `Exception`** được công bố trong chữ ký, dù bên trong có lúc chỉ ném một unchecked exception. Hợp đồng khai báo có ý nghĩa riêng.

### Ghi đè phương thức và `throws`

Quy tắc ghi đè liên quan exception checked: phương thức override thường không được thêm một checked exception rộng hơn những gì phương thức cha cho phép. Nhưng unchecked exception không bị giới hạn bởi quy tắc này.

Ví dụ mã Java hợp lệ:

```java
class ParentWorker {
    void execute() {
        // Hợp đồng không có checked exception.
    }
}

class ChildWorker extends ParentWorker {
    @Override
    void execute() throws IllegalStateException {
        throw new IllegalStateException("Chưa khởi tạo");
    }
}
```

Đây là lớp minh họa không có `main`. `IllegalStateException` là unchecked nên chữ ký override hợp lệ. Nếu thay bằng `throws IOException`, mã này sẽ không biên dịch vì khai báo checked exception mới mà phương thức cha không cho phép.

## 10. Thiết kế xử lý `RuntimeException` đúng tầng

Tầng phát hiện và tầng quyết định phản hồi có thể khác nhau:

1. **Lớp thư viện/API:** kiểm tra đối số và bất biến, ném `IllegalArgumentException` hoặc `IllegalStateException` khi hợp đồng bị vi phạm; chọn loại cụ thể và thông điệp hữu ích.
2. **Tầng nhận yêu cầu:** xác thực dữ liệu người dùng, chuyển lỗi parse thành thông điệp có cấu trúc khi đó là trường hợp dự kiến. Không hiển thị stack trace cho người dùng.
3. **Tầng nghiệp vụ:** trả trạng thái domain cho nhánh từ chối hợp lệ; giữ lỗi kỹ thuật/bất biến riêng.
4. **Ranh giới ứng dụng:** ghi log nguyên nhân, phân loại phản hồi, dừng yêu cầu hoặc đánh dấu job thất bại đúng chính sách.

Với HTTP API, việc trả `400` cho dữ liệu nhập không hợp lệ, `409` cho xung đột nghiệp vụ hoặc `500` cho lỗi nội bộ là **lựa chọn hợp đồng API**, không phải quy tắc tự động của Java. Cùng `IllegalArgumentException` có thể xuất phát từ nhập liệu hoặc bug nội bộ; chỉ dựa vào tên lớp để trả `400` có thể che khuất lỗi lập trình.

**Không dùng unchecked exception làm đường tắt cho mọi vấn đề**. Nếu một thư viện ném `IOException`, thay nó bằng `RuntimeException` không tự tạo chiến lược phục hồi. Chỉ chuyển loại khi cần ranh giới trừu tượng phù hợp và bảo toàn nguyên nhân qua `cause`.

**Không nên log cùng một exception đầy đủ ở mọi tầng**, vì tạo nhiều bản ghi trùng nhau; chọn nơi có đủ ngữ cảnh, giữ stack trace/cause cần thiết, không lộ mật khẩu, token hoặc dữ liệu nhạy cảm.

## 11. Sai lầm thường gặp

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “Unchecked tức là JVM không phát hiện.” | JVM vẫn ném exception; chỉ không có nghĩa vụ `catch-or-declare` ở compiler. |
| “Mọi lớp con của `Exception` là checked.” | `RuntimeException` và các lớp con là unchecked. |
| “`RuntimeException` và `Error` nên bắt như nhau.” | Chúng cùng unchecked nhưng `Error` thường cho thấy vấn đề rất nghiêm trọng, khó tiếp tục an toàn. |
| “Không có `throws` nghĩa là phương thức không ném exception.” | Unchecked exception có thể xuất hiện không cần khai báo. |
| “Thêm `throws RuntimeException` buộc caller bắt.” | Không; unchecked vẫn không bị quy tắc bắt/khai báo bắt buộc. |
| “`catch (Exception e)` bắt được `OutOfMemoryError`.” | Không, vì `Error` nằm ngoài nhánh `Exception`. |
| “Bắt `Throwable` để ứng dụng không thể sập.” | Có thể nuốt lỗi nghiêm trọng, cố tiếp tục khi trạng thái JVM không an toàn. |
| “`NoClassDefFoundError` và `ClassNotFoundException` là cùng loại.” | Một bên là unchecked `Error`, bên kia là checked `Exception`. |
| “`assert` thay thế mọi validation.” | Assertions có thể bị tắt; không dùng để kiểm tra dữ liệu không tin cậy. |
| “Mỗi lỗi người dùng đều là bug.” | Có thể chuyển exception parse sang kết quả xác thực dự kiến ở ranh giới phù hợp. |
| “`Error` có nghĩa compile error.” | `Error` là lớp Java, còn compile error là chẩn đoán của trình biên dịch. |
| “Bắt exception rồi bỏ qua nghĩa là đã xử lý.” | Có thể làm mất nguyên nhân, trả kết quả giả và khiến trạng thái tiếp tục sai. |

## 12. Câu hỏi và tình huống luyện tập

**1. `NumberFormatException` có checked không?**  
Không. Nó là lớp con của `IllegalArgumentException`, tiếp tục kế thừa `RuntimeException`.

**2. `NullPointerException` có cần khai báo trong `throws` của mọi phương thức có thể ném nó không?**  
Không. Có thể tài liệu hóa hợp đồng bằng chú thích hoặc thiết kế API rõ ràng, nhưng trình biên dịch không đòi hỏi khai báo unchecked exception.

**3. `IOException` có unchecked vì đôi khi xảy ra lúc runtime không?**  
Không. “Checked/unchecked” được xác định từ phân cấp `Throwable`, không phải thời điểm thực thi: `IOException` là checked.

**4. Đặt `catch (IllegalArgumentException e)` trước `catch (NumberFormatException e)` có hợp lệ không?**  
Không nếu hai nhánh kế tiếp cùng thuộc một `try` theo thứ tự đó. Nhánh cho lớp con không thể tới vì lớp cha đã bắt nó.

**5. Tại sao không nên dùng `catch (Error e)` cho mọi thao tác?**  
Vì nhiều `Error` báo sự cố nền tảng, như JVM hết bộ nhớ hoặc lỗi liên kết lớp. Bắt chúng không khắc phục nguyên nhân và có thể tiếp tục trong trạng thái hỏng.

**6. `assert condition` luôn kiểm tra `condition` không?**  
Không. Việc thực thi assertion phụ thuộc cấu hình bật/tắt (`-ea` và các tùy chọn tương ứng). Do đó không thay kiểm tra đầu vào hoặc điều kiện bảo mật bằng assertion.

**7. Lỗi không tìm được lớp khi `Class.forName` được gọi có luôn là `NoClassDefFoundError` không?**  
Không. `Class.forName` có thể ném checked `ClassNotFoundException`; `NoClassDefFoundError` là lỗi khác trong nhánh `LinkageError`.

**8. Khi trạng thái đơn hàng đã SHIPPED, có bắt buộc ném custom unchecked exception không?**  
Không. Có thể dùng kết quả domain thông thường hoặc exception tùy hợp đồng và ý nghĩa của lời gọi sai trạng thái.

**9. Chỉ cần xóa `throws IOException` khỏi hàm đọc tệp để chuyển nó thành unchecked không?**  
Không. Nếu bên trong vẫn gọi API có checked `IOException` mà không xử lý, phương thức sẽ không biên dịch. Muốn đổi hợp đồng cần bắt và xử lý/chuyển đổi một cách có chủ ý.

**10. Một unchecked exception bị bỏ qua sẽ làm toàn bộ JVM kết thúc trong mọi trường hợp không?**  
Không. Nó lan tới `catch` hoặc ranh giới xử lý; nếu thoát khỏi một thread, thread đó có thể kết thúc, trong khi các thread khác vẫn tồn tại. Ứng dụng console đơn giản có thể kết thúc khi exception thoát khỏi `main`.

## 13. Tự kiểm tra trước khi chọn xử lý

Khi thấy một lỗi, xác định ba vấn đề theo thứ tự:

- **Nó thuộc nhánh nào?** `RuntimeException`, `Error`, hay checked exception khác? Phân cấp xác định nghĩa vụ của compiler.
- **Nguyên nhân và phạm vi ảnh hưởng là gì?** Đầu vào sai, hợp đồng bị vi phạm, trạng thái sai, thư viện thiếu, JVM cạn nguồn lực hay một bất biến bị phá vỡ?
- **Tầng hiện tại có khả năng xử lý an toàn không?** Nếu có, bắt đúng loại và đưa ra phản hồi/khôi phục có ý nghĩa. Nếu không, cho phép lỗi lan tới ranh giới có chính sách phù hợp; đối với nhiều `Error`, phải sửa nguyên nhân và đánh giá lại khả năng tiếp tục hoạt động.

**Ghi nhớ:** `RuntimeException` và `Error` cùng là **unchecked**, vì Java không bắt buộc caller bắt hoặc khai báo chúng. Sự khác nhau về ý nghĩa và khả năng phục hồi mới là cơ sở chọn cách xử lý. Đọc đúng hệ phân cấp giúp tránh đánh đồng dữ liệu đầu vào sai với lỗi JVM, tránh bắt quá rộng, và thiết kế API có hợp đồng rõ ràng.
