# Giới hạn lớp generic liên quan đến Throwable

## 1. Quy tắc cần phân biệt ngay từ đầu

Java cấm một lớp tổng quát (generic class) là lớp con **trực tiếp hoặc gián tiếp** của `Throwable`. Quy tắc áp dụng cho cả các nhánh `Exception`, `RuntimeException` và `Error`.

Ví dụ cố ý không biên dịch:

```java
class PayloadException<T> extends Exception {
}
```

Nhưng Java vẫn cho phép dùng kiểu ngoại lệ làm **đối số kiểu** hoặc **cận của biến kiểu**:

```java
class FailureHolder<E extends Exception> {
    private final E failure;

    FailureHolder(E failure) {
        this.failure = failure;
    }

    E failure() {
        return failure;
    }
}
```

`FailureHolder<E>` hợp lệ vì nó chỉ chứa một ngoại lệ; nó không kế thừa `Throwable`.

Ba thao tác dưới đây cũng cần tách riêng:

| Cách sử dụng | Có hợp lệ không? |
| --- | --- |
| Khai báo `class Problem<T> extends Exception` | Không |
| Khai báo `<E extends Exception>` trên lớp hoặc phương thức thông thường | Có |
| Ghi `throws E` khi `E` có cận phù hợp | Có |
| `throw failure` khi biểu thức có kiểu `E extends Throwable` | Có |
| `catch (E failure)` khi `E` là biến kiểu | Không |

Bài này giải thích vì sao những trường hợp có vẻ gần nhau lại khác nhau, rồi dùng một API tổng quát để giữ nguyên kiểu ngoại lệ được kiểm tra. Các quy tắc vẫn áp dụng trên Java hiện đại; ví dụ chạy độc lập dùng Java 17+.

## 2. Vì sao không có Exception<T>?

Cơ chế chọn nhánh `catch` của JVM dựa vào lớp thực tế của đối tượng được ném và quan hệ kế thừa với lớp ngoại lệ trong bộ xử lý.

Trong khi đó, xóa kiểu không tạo ra các lớp thực thi riêng cho từng đối số kiểu như `PayloadException<String>` và `PayloadException<Integer>`. Nếu cho phép khai báo đó, việc bắt hai biến thể theo đối số kiểu sẽ không có cơ sở phân biệt tương ứng ở cơ chế bắt ngoại lệ thông thường.

Ý định sau vì thế không thể được thiết kế theo kiểu “ngoại lệ tổng quát”:

```java
// Ý tưởng không hợp lệ; không phải mã có thể chạy:
// catch (PayloadException<String> failure) { }
// catch (PayloadException<Integer> failure) { }
```

Java chặn từ khai báo lớp con tổng quát của `Throwable`, chứ không chỉ chặn một vài cách viết `catch`.

Điều bị mất ở đây là sự phân biệt theo **đối số kiểu tổng quát**, không phải lớp thực tế của mọi ngoại lệ. Một đối tượng `IOException` vẫn có lớp thực tế là `IOException`; xóa kiểu không biến nó thành một đối tượng lớp `Exception`.

Sơ đồ cần giữ:

```text
IOException thực tế được ném
        ↓
JVM kiểm tra quan hệ lớp
        ↓
catch (IOException failure) có thể tiếp nhận

Biến kiểu E trong mã nguồn
        ↓
Không phải một lớp ngoại lệ riêng có thể dùng làm catch
```

## 3. Phạm vi của điều cấm

### 3.1. Kế thừa gián tiếp cũng bị cấm

Không thể né quy tắc bằng một lớp trung gian:

```java
class BaseProblem extends Exception {
    private static final long serialVersionUID = 1L;
}

// Không biên dịch:
// class DetailedProblem<T> extends BaseProblem { }
```

`DetailedProblem<T>` vẫn là lớp con gián tiếp của `Throwable`.

Đổi `Exception` thành `RuntimeException` không làm quy tắc biến mất:

```java
// Đều không hợp lệ:
// class UncheckedProblem<T> extends RuntimeException { }
// class FatalProblem<T> extends Error { }
// class DirectProblem<T> extends Throwable { }
```

Đây là giới hạn về dạng lớp trong phân cấp `Throwable`, không phải giới hạn chỉ dành cho ngoại lệ được kiểm tra (checked exception).

### 3.2. Lớp bên trong một lớp tổng quát cũng cần chú ý

Trường hợp này bị `javac` từ chối dù `Problem` không tự viết `<T>`:

```java
// Ví dụ cố ý không biên dịch.
class Container<T> {
    class Problem extends Exception {
        private static final long serialVersionUID = 1L;
    }
}
```

`Problem` là lớp thành viên không `static`, gắn với thể hiện của kiểu bao tổng quát `Container<T>`. Việc chỉ bỏ danh sách tham số kiểu trên tên lớp ngoại lệ chưa tách nó khỏi ngữ cảnh tổng quát đó.

Nếu ngoại lệ không cần gắn với thể hiện của lớp bao, có thể dùng lớp lồng `static` không tổng quát hoặc một lớp riêng:

```java
class Container<T> {
    static class Problem extends Exception {
        private static final long serialVersionUID = 1L;

        Problem(String message) {
            super(message);
        }
    }
}
```

Đoạn sửa này hợp lệ. Ngoại lệ không được dùng `T` của lớp bao như kiểu dữ liệu thành viên riêng của nó. Việc chuyển sang `static` là lựa chọn mô hình phù hợp khi không cần quan hệ với thể hiện lớp bao, không phải cách tạo một ngoại lệ tổng quát.

### 3.3. Lớp ngoại lệ không tổng quát vẫn có thể có phương thức tổng quát

Một phương thức hoặc hàm tạo có tham số kiểu không tự biến lớp chứa nó thành một lớp tổng quát. Quy tắc cấm áp dụng cho **lớp** tổng quát trong phân cấp `Throwable`.

Tuy nhiên, thêm phương thức tổng quát không tạo ra các biến thể ngoại lệ có thể bắt theo `String`, `Integer`… trong `catch`. Hãy dùng khả năng đó khi phương thức thực sự cần quan hệ kiểu riêng, không để giả lập một lớp `Exception<T>`.

## 4. Có thể ném E và khai báo throws E

Một phương thức được phép nhận rồi ném lại ngoại lệ có kiểu tổng quát:

```java
static <E extends Throwable> void rethrow(E failure) throws E {
    throw failure;
}
```

`E extends Throwable` bảo đảm giá trị thuộc phân cấp mà câu lệnh `throw` chấp nhận. `throws E` giữ quan hệ giữa kiểu đầu vào và hợp đồng ngoại lệ của phương thức.

Ví dụ dùng `IOException`:

```java
IOException original = new IOException("disk unavailable");

try {
    rethrow(original);
} catch (IOException failure) {
    System.out.println(failure == original); // true
}
```

Đoạn này cần import `java.io.IOException` và phương thức `rethrow` ở cùng ngữ cảnh thích hợp.

Phương thức không tạo ngoại lệ mới, không bọc nguyên nhân và không đổi lớp của đối tượng. Nó ném lại cùng tham chiếu.

Nếu một API chỉ muốn mô hình hóa các ngoại lệ ứng dụng thông thường, có thể chọn cận `E extends Exception`. Cận `Throwable` rộng hơn, bao gồm cả `Error`; hãy chọn phạm vi theo hợp đồng API chứ không chọn cận rộng nhất theo thói quen.

### 4.1. Vì sao throws E hợp lệ nhưng catch E không hợp lệ?

Hai vị trí làm công việc khác nhau:

- `throws E` biểu đạt hợp đồng ngoại lệ để trình biên dịch kiểm tra nơi gọi.
- `catch (E failure)` sẽ yêu cầu cơ chế chọn bộ xử lý theo một biến kiểu không đại diện cho lớp ngoại lệ cụ thể tại runtime.

Ví dụ cố ý không hợp lệ:

```java
static <E extends Exception> void invalidCatch() {
    try {
        throw new IllegalStateException("failure");
    } catch (E failure) { // Không biên dịch: E là biến kiểu.
    }
}
```

Không sửa bằng cách đổi tên `E` thành `T` hoặc thêm cận hẹp hơn. Nếu kiểu trong `catch` vẫn là biến kiểu, quy tắc vẫn áp dụng.

## 5. Mẫu API hợp lệ: truyền tiếp đúng kiểu ngoại lệ

Một interface hàm tổng quát có thể mô tả cả kết quả lẫn kiểu ngoại lệ:

```java
@FunctionalInterface
interface CheckedSupplier<T, E extends Exception> {
    T get() throws E;
}

static <T, E extends Exception> T call(CheckedSupplier<T, E> action)
        throws E {
    return action.get();
}
```

Interface không kế thừa `Throwable`; nó chỉ dùng `E` trong hợp đồng của `get`. Phương thức `call` không cần bắt `E`; nó truyền ngoại lệ lên nơi gọi bằng `throws E`.

Luồng dữ liệu và lỗi:

```text
CheckedSupplier<T, E>
    ├── thành công → T → call trả về T
    └── thất bại   → E → call ném tiếp E
```

Ví dụ:

```java
CheckedSupplier<String, IOException> read = () -> {
    throw new IOException("read failed");
};

try {
    String value = call(read);
} catch (IOException failure) {
    System.out.println(failure.getMessage());
}
```

Kiểu khai báo của `read` giữ rõ `E = IOException`, nên nơi gọi có thể bắt `IOException`.

Nếu đổi nó thành `CheckedSupplier<String, Exception>`, hợp đồng tĩnh rộng hơn: nơi gọi phải xử lý hoặc khai báo `Exception` theo hợp đồng đó. Việc mở rộng tên kiểu không thay đổi lớp thực tế của đối tượng lỗi; nó thay đổi điều trình biên dịch có thể bảo đảm.

### 5.1. Supplier<T> chuẩn không có throws E

`java.util.function.Supplier<T>` có `get()` không khai báo ngoại lệ được kiểm tra. Vì vậy, một lambda ném `IOException` không tự nhiên phù hợp với hợp đồng đó.

Nếu cần giữ kiểu ngoại lệ được kiểm tra trong một API tổng quát, interface có `E` như trên là một lựa chọn rõ ràng. Nếu API cần chuyển lỗi sang một ngoại lệ nghiệp vụ khác, hãy bọc có chủ đích và giữ `cause`; đừng dùng cast không được kiểm tra để giấu hợp đồng lỗi.

## 6. Thiết kế dữ liệu lỗi khi không thể dùng Exception<T>

### 6.1. Ngoại lệ cụ thể với trường dữ liệu có kiểu rõ ràng

Thay vì một `ValidationException<T>`, có thể định nghĩa một ngoại lệ không tổng quát với các trường phù hợp nghiệp vụ:

```java
final class ValidationException extends Exception {
    private static final long serialVersionUID = 1L;

    private final String field;

    ValidationException(String field, String message) {
        super(message);
        this.field = field;
    }

    String field() {
        return field;
    }
}
```

Nơi gọi bắt `ValidationException` rồi đọc `field()`. Kiểu ngoại lệ thể hiện loại lỗi; trường dữ liệu cung cấp chi tiết để xử lý.

Nếu cần giữ một nguyên nhân gốc, thêm hàm tạo nhận `Throwable cause` và gọi `super(message, cause)`. Việc chứa một `Throwable` là hợp lệ, giống như việc một lớp bình thường chứa `E extends Exception`.

### 6.2. Khi dữ liệu lỗi cần tổng quát, tách khỏi đối tượng được ném

Một cấu trúc như `FailureData<T>` có thể là lớp dữ liệu tổng quát thông thường, miễn không kế thừa `Throwable`. Thuật toán có thể trả một mô hình kết quả mang dữ liệu lỗi có kiểu nếu đó là hợp đồng phù hợp.

Nếu vẫn dùng ngoại lệ, hãy giữ kiểu ngoại lệ và thông tin nghiệp vụ rõ ràng. Việc cho một getter trả `Object` rồi cast ở mọi nơi không khôi phục khả năng bắt `Exception<T>`, mà chỉ đẩy việc kiểm tra dữ liệu sang runtime.

Không cần cố biến mọi kết quả lỗi thành exception; cũng không cần đổi toàn bộ API sang mô hình kết quả chỉ vì có giới hạn này. Chọn theo cách nơi gọi thật sự phục hồi hoặc phản hồi lỗi.

## 7. Chương trình hoàn chỉnh

Lưu thành `ThrowableGenericsDemo.java`:

```java
import java.io.IOException;

public class ThrowableGenericsDemo {
    @FunctionalInterface
    interface CheckedSupplier<T, E extends Exception> {
        T get() throws E;
    }

    static <T, E extends Exception> T call(CheckedSupplier<T, E> action)
            throws E {
        return action.get();
    }

    static <E extends Throwable> void rethrow(E failure) throws E {
        throw failure;
    }

    static final class ValidationException extends Exception {
        private static final long serialVersionUID = 1L;

        private final String field;

        ValidationException(String field, String message) {
            super(message);
            this.field = field;
        }

        String field() {
            return field;
        }
    }

    public static void main(String[] args) {
        String ready = call(() -> "ready");
        System.out.println("success = " + ready);

        CheckedSupplier<String, IOException> read = () -> {
            throw new IOException("read failed");
        };

        try {
            call(read);
        } catch (IOException failure) {
            System.out.println("io = " + failure.getMessage());
        }

        CheckedSupplier<Integer, ValidationException> validate = () -> {
            throw new ValidationException("email", "invalid address");
        };

        try {
            call(validate);
        } catch (ValidationException failure) {
            System.out.println("validation = "
                    + failure.field() + ": " + failure.getMessage());
        }

        IOException original = new IOException("same instance");
        try {
            rethrow(original);
        } catch (IOException failure) {
            System.out.println("same exception = " + (failure == original));
        }
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```shell
javac --release 17 -Xlint:all ThrowableGenericsDemo.java
java ThrowableGenericsDemo
```

Stdout chính xác:

```text
success = ready
io = read failed
validation = email: invalid address
same exception = true
```

Không có lớp ngoại lệ tổng quát nào trong chương trình. Generics nằm ở interface hành động và các phương thức giữ hợp đồng. Những đối tượng thật được ném là `IOException` và `ValidationException`, rồi được bắt bằng các lớp cụ thể đó.

Ở lời gọi thành công, lambda không ném ngoại lệ được kiểm tra, nên trình biên dịch không buộc `main` thêm một `catch Exception` chỉ vì phương thức `call` có tham số kiểu `E`. Với hai hành động được gán vào biến có kiểu rõ ràng, hợp đồng lỗi được giữ theo từng khai báo.

## 8. Lỗi suy luận thường gặp

### 8.1. “Throwable không generic nên không được dùng làm cận”

Sai. `E extends Throwable` ràng buộc `E` là kiểu ngoại lệ phù hợp, không khai báo một lớp tổng quát kế thừa `Throwable`. Đây là hai cấu trúc khác nhau.

### 8.2. “Unchecked exception không chịu giới hạn”

Sai. `RuntimeException` vẫn nằm trong phân cấp `Throwable`; một lớp `Problem<T> extends RuntimeException` vẫn bị cấm.

### 8.3. “throws E biến ngoại lệ thành E lúc chạy”

Sai. Nó giữ quan hệ kiểu trong hợp đồng biên dịch. Đối tượng được ném vẫn có lớp thực tế của nó, và `catch` tiếp tục hoạt động theo quan hệ lớp.

### 8.4. “Bắt Exception rồi cast sang E là tương đương catch E”

Không tương đương. `catch (Exception failure)` đã bắt theo lớp `Exception`. Một cast không được kiểm tra sau đó không làm JVM lọc ngoại lệ theo đối số kiểu mà mã nguồn mong muốn.

Nếu muốn chọn theo một lớp được truyền lúc chạy, có thể thiết kế API nhận `Class<E>` rồi kiểm tra tường minh, nhưng đó vẫn là logic sau khi bắt một lớp cụ thể; nó không tạo cú pháp `catch (E ...)` hợp lệ. Thường nên bắt lớp ngoại lệ cụ thể tại nơi có đủ ngữ cảnh.

### 8.5. “Chỉ cần đổi Exception<T> thành Exception<?>”

Không thể: lớp ngoại lệ tổng quát đã không được phép khai báo. Wildcard không thay đổi giới hạn kế thừa `Throwable` và không tạo một lớp ngoại lệ có thể phân biệt theo đối số kiểu.

## 9. Tự kiểm tra trước khi viết API

Với một thiết kế có generics và ngoại lệ, hãy kiểm tra:

1. Lớp nào thực sự kế thừa `Throwable`? Lớp đó phải không tổng quát.
2. Biến kiểu `E` đang mô tả hợp đồng `throws` hay đang bị dùng làm kiểu `catch`?
3. API có giữ kiểu ngoại lệ cụ thể cần thiết, hay đã mở rộng mọi lỗi thành `Exception`?
4. Dữ liệu lỗi nên là trường có kiểu nghiệp vụ, một nguyên nhân gốc hay một mô hình kết quả riêng?
5. Mã nguồn có giữ nguyên kiểm tra ngoại lệ của trình biên dịch, hay đang dùng cast để che giấu nó?

Câu trả lời đúng thường là một lớp ngoại lệ cụ thể cộng với phương thức tổng quát truyền tiếp kiểu lỗi, như ví dụ trên.

## Tài liệu đối chiếu

- [JLS §8.1.2 — Generic Classes and Type Parameters](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.1.2): cấm lớp tổng quát là lớp con trực tiếp hoặc gián tiếp của `Throwable`.
- [JLS §8.4.6 — Method Throws](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.4.6): cho phép biến kiểu trong `throws`.
- [JLS §14.20 — The try Statement](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.20): cấm biến kiểu trong tham số `catch`.
- [Java Throwable API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Throwable.html): phân cấp đối tượng được ném và cơ chế giữ nguyên nhân.
