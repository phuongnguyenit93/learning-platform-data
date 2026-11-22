# Giới hạn `Throwable` trong `throws` của phương thức generic (Java)

## 1. Mục tiêu và ý nghĩa

Trong Java, phương thức generic có thể khai báo một **tham số kiểu đại diện cho loại ngoại lệ** mà phương thức có khả năng ném. Thay vì công bố một ngoại lệ quá rộng như `throws Exception`, ta có thể viết `throws E` để bảo toàn thông tin loại ngoại lệ từ thao tác bên trong đến nơi gọi.

Sau bài này, bạn cần hiểu:

- Điều kiện để một type variable hợp lệ trong `throws` và sự khác nhau giữa `Throwable`, `Exception`, `RuntimeException`.
- Compiler kiểm tra checked exception như thế nào khi `E` là một type variable.
- Cách truyền ngoại lệ qua callback/lambda bằng generic method mà không buộc caller xử lý `Exception` quá rộng.
- Vì sao không thể `catch (E e)` hoặc tạo `Exception<T>` kế thừa `Throwable`; những lỗi thường gặp về suy luận kiểu.

## 2. Quy tắc nền tảng của Java

Theo Java Language Specification (JLS) §8.4.6, mỗi loại nằm trong mệnh đề `throws` phải là **lớp ngoại lệ** hoặc **type variable có kiểu con của `Throwable`**. Vì vậy, cú pháp cơ bản là:

~~~java
static <E extends Throwable> void raise(E error) throws E {
    throw error;
}
~~~

Trong khai báo này:

1. `<E extends Throwable>` khai báo tham số kiểu của **phương thức**, giới hạn `E` ở các kiểu dẫn xuất của `Throwable`.
2. Tham số `E error` buộc đối tượng truyền vào có kiểu phù hợp với `E`.
3. `throw error` ném **đối tượng thực tế**; `throws E` công bố khả năng đó với compiler và caller.
4. `E` được xác định qua đối số, type argument tường minh hoặc ngữ cảnh suy luận kiểu. `E` không phải một lớp ngoại lệ mới.

Có thể dùng giới hạn cụ thể hơn:

~~~java
static <E extends Exception> void perform(E error) throws E {
    throw error;
}

static <E extends java.io.IOException> void ioOnly(E error) throws E {
    throw error;
}
~~~

| Khai báo giới hạn | `E` có thể biểu diễn | Ý nghĩa thực tế |
| --- | --- | --- |
| `E extends Throwable` | `Exception`, `Error` và các lớp con | Rộng nhất; chỉ chọn khi API thực sự cần truyền cả `Error`. |
| `E extends Exception` | Checked exception thuộc nhánh `Exception` và `RuntimeException` | Thường phù hợp cho callback có thể thất bại. |
| `E extends IOException` | `IOException` và lớp con | Giới hạn vào họ lỗi I/O. |
| `E extends RuntimeException` | Các ngoại lệ runtime | Chỉ thuộc nhóm unchecked exception; caller không bị buộc khai báo/bắt. |

**Checked và unchecked:** `RuntimeException` cùng các lớp con, và `Error` cùng các lớp con là unchecked. Những kiểu con khác của `Throwable` thuộc nhóm checked; compiler bắt buộc phải chứng minh chúng được bắt hoặc khai báo. Không phải mọi `E extends Exception` đều checked, vì `RuntimeException extends Exception`.

Một tham số kiểu không giới hạn được ngầm hiểu là `Object`, nên `<E> void f() throws E` **không hợp lệ**: compiler không thể bảo đảm `E` là kiểu con của `Throwable`. Tương tự, `String`, `Object` hoặc kiểu parameterized không phải ngoại lệ đều không thể đứng trong `throws`.

## 3. `throws E` lan truyền checked exception ra caller như thế nào?

Giả sử ta gọi:

~~~java
try {
    raise(new java.io.IOException("network unavailable"));
} catch (java.io.IOException ex) {
    System.out.println(ex.getMessage());
}
~~~

Compiler suy luận `E` từ đối tượng `IOException`. Do `IOException` là checked exception, nơi gọi phải bắt hoặc khai báo tương ứng. Mệnh đề `throws E` không làm ngoại lệ thành unchecked và không che được quy tắc kiểm tra checked exception.

Khi caller có thể chọn chính xác `E`, nó cũng có thể truyền type argument tường minh, chẳng hạn `GenericThrowsDemo.<IOException>raise(...)` nếu `raise` được khai báo trong lớp `GenericThrowsDemo`. Type argument phải thỏa ràng buộc kiểu và tương thích với các đối số thực tế.

**Chi tiết quan trọng:** `throws E` chỉ *khai báo loại ngoại lệ có thể phát sinh*. Nó không tự chứng minh mọi `throw new IOException(...)` trong thân phương thức đều hợp lệ khi `E extends Exception`, vì người gọi có thể chọn `E = java.sql.SQLException`. Thân phương thức phải ném đối tượng có kiểu tương thích với **mọi** cách gán `E` hợp lệ, hoặc khai báo/bắt ngoại lệ cụ thể riêng.

## 4. Ví dụ chạy được: giữ đúng loại checked exception qua callback

Trong ví dụ dưới đây, `ThrowingSupplier<T, E>` có thể trả về `T` hoặc ném `E`. Phương thức generic `execute` giữ nguyên hợp đồng này; lambda gọi một thao tác có `IOException`, nên caller bắt được `IOException` cụ thể.

Lưu tệp **GenericThrowsDemo.java**:

~~~java
import java.io.IOException;

public class GenericThrowsDemo {
    @FunctionalInterface
    interface ThrowingSupplier<T, E extends Exception> {
        T get() throws E;
    }

    static <T, E extends Exception> T execute(ThrowingSupplier<T, E> work) throws E {
        return work.get();
    }

    static String read(boolean fail) throws IOException {
        if (fail) {
            throw new IOException("read failed");
        }
        return "OK";
    }

    public static void main(String[] args) {
        try {
            System.out.println("Result: " + execute(() -> read(false)));
            execute(() -> read(true));
        } catch (IOException ex) {
            System.out.println("Caught IOException: " + ex.getMessage());
        }
    }
}
~~~

Biên dịch và chạy với Java 17 trở lên:

~~~bash
javac -encoding UTF-8 GenericThrowsDemo.java
java GenericThrowsDemo
~~~

Kết quả chuẩn:

~~~text
Result: OK
Caught IOException: read failed
~~~

Diễn tiến:

1. `read(false)` trả về chuỗi `OK`, nên `execute` trả về bình thường.
2. `read(true)` ném một `IOException`. `get() throws E` cho phép `execute` truyền lỗi này ra ngoài.
3. Compiler dùng ràng buộc của lambda để suy luận `E` thích hợp; `catch (IOException ex)` xử lý đúng lỗi trong ví dụ.
4. Nếu bỏ xử lý checked exception này, caller phải khai báo `throws IOException` (hoặc kiểu cha phù hợp), hoặc biên dịch sẽ thất bại.

So với API chỉ viết `static <T> T execute(Callable<T> work) throws Exception`, giải pháp giữ type variable `E` giúp caller sử dụng kiểu checked exception cụ thể hơn thay vì phải xử lý `Exception` bao quát. Lưu ý `java.util.concurrent.Callable.call()` được khai báo `throws Exception`; viết một interface có `E` riêng là cách giữ chính xác hợp đồng ngoại lệ của callback.

## 5. Các giới hạn cần nhớ

### 5.1. `E` phải có bound hợp lệ

Các khai báo sau không hợp lệ:

~~~java
// SAI: E mặc định extends Object, không bảo đảm là Throwable.
static <E> void bad1() throws E {}

// SAI: String không kế thừa Throwable.
static void bad2() throws String {}

// SAI: T chỉ là kiểu dữ liệu tùy ý, không thể được sử dụng làm loại ngoại lệ.
static <T> void bad3(T value) throws T {}
~~~

Cách đúng là khai báo giới hạn, ví dụ `<E extends Exception>` hoặc `<E extends Throwable>`, và bảo đảm thân phương thức tuân thủ hợp đồng.

### 5.2. Không thể bắt bằng `catch (E e)`

Đoạn sau **không biên dịch**:

~~~java
static <E extends Exception> void broken(E error) {
    try {
        throw error;
    } catch (E ex) { // SAI: không được dùng type variable ở kiểu của catch
        System.out.println(ex.getMessage());
    }
}
~~~

JLS §14.20 yêu cầu kiểu ngoại lệ trong `catch` phải là một kiểu lớp thích hợp, không phải type variable. Có thể bắt lớp xác định `catch (Exception ex)` hoặc để ngoại lệ lan ra bằng `throws E`. Khi cần bắt chung, cân nhắc rằng bắt `Exception` có phạm vi rộng và không bao gồm `Error`.

### 5.3. Không thể tạo lớp ngoại lệ generic

Khai báo sau **không hợp lệ**:

~~~java
// SAI: lớp generic không được trực tiếp hoặc gián tiếp kế thừa Throwable.
class AppFailure<T> extends Exception {}
~~~

Có thể định nghĩa một lớp ngoại lệ **không generic** và lưu thông tin bổ sung trong các trường có kiểu xác định; hoặc dùng đối tượng kết quả generic, ví dụ `Result<T>`, nếu nghiệp vụ cần mang dữ liệu có kiểu.

### 5.4. Không thể tự ý tạo `new E()` hoặc ném một subtype bất kỳ

~~~java
// SAI: IOException không nhất thiết là một E cụ thể.
static <E extends Exception> void brokenThrow() throws E {
    throw new java.io.IOException("read failed");
}

// SAI: Java không cho gọi constructor của type variable.
static <E extends Exception> void brokenNew() throws E {
    throw new E();
}
~~~

Dùng một đối tượng `E` do caller truyền vào, gọi callback khai báo `throws E`, hoặc nếu thực sự luôn ném `IOException` thì khai báo `throws IOException` trực tiếp. Đừng thêm generic vào API khi không có thông tin ngoại lệ cần truyền xuyên qua.

### 5.5. Checked exception khi override vẫn bị giới hạn

Generic không cho phép phương thức override mở rộng tập checked exception vượt quá hợp đồng của phương thức cha/interface. Khi override, compiler vẫn áp dụng quy tắc tương thích `throws` của JLS §8.4.8.3. Nếu một interface không cho ném checked exception, không thể biến việc override thành hợp lệ chỉ bằng cách khai báo thêm `<E extends Exception> ... throws E`.

## 6. Cẩn thận với suy luận kiểu và cách “sneaky throw”

Suy luận kiểu generic có quy tắc đặc biệt với type variable xuất hiện trong `throws`. Theo JLS §18.1.3 và §18.4, khi không có ràng buộc khác chặt hơn, compiler có thể chọn `RuntimeException` cho biến suy luận xuất hiện trong `throws` và có các upper bound phù hợp. Đây **không phải** phép chuyển một `IOException` thành `RuntimeException` tại runtime.

Một mẫu nguy hiểm là:

~~~java
@SuppressWarnings("unchecked")
static <E extends Throwable> void sneakyThrow(Throwable error) throws E {
    throw (E) error;
}
~~~

Ở đây kiểu `E` **không xuất hiện trong tham số truyền vào**; phép ép kiểu `(E) error` là unchecked. Lời gọi không nêu type argument có thể được suy luận với `E = RuntimeException`, trong khi đối tượng thật vẫn là một checked exception (chẳng hạn `IOException`) khi chạy. Điều này phá kỳ vọng xử lý checked exception ở call site; **không nên áp dụng như một cách “lách” checked exception trong API thông thường**.

Hãy so sánh với phiên bản an toàn hơn:

~~~java
static <E extends Throwable> void throwExact(E error) throws E {
    throw error;
}
~~~

Với `throwExact(new IOException("failed"))`, kiểu của đối số buộc suy luận phản ánh `IOException`. Không nên suy đoán kiểu suy luận bằng trực giác khi dùng lambda hoặc nhiều nguồn lỗi: hãy kiểm tra khai báo phương thức, các ràng buộc và lỗi biên dịch tại call site.

## 7. Khi nào nên dùng `throws E`?

**Nên dùng** khi thiết kế helper điều phối thao tác có thể ném những loại checked exception khác nhau: callback, template method, xử lý tài nguyên với contract riêng, hoặc phương thức chuyển tiếp lỗi đã được định kiểu. Ví dụ điển hình là cặp `ThrowingSupplier<T, E>` và `execute(...) throws E`.

**Nên dùng `throws IOException`, `SQLException` hoặc một lớp lỗi cụ thể** khi phương thức có một tập lỗi xác định và không cần bảo toàn kiểu ngoại lệ từ một callback hay đối số generic. API càng chính xác và đơn giản càng dễ sử dụng.

**Tránh** giới hạn `E extends Throwable` khi chỉ định xử lý các lỗi nghiệp vụ: `Throwable` bao gồm cả `Error` vốn thường biểu thị lỗi nghiêm trọng mà ứng dụng không nên bắt để phục hồi. `E extends Exception` thường truyền đạt ý định tốt hơn.

## 8. Kiểm tra hiểu bài

1. Vì sao `<E> void run() throws E` không biên dịch? **Vì `E` mặc định có bound `Object`, không được bảo đảm là subtype của `Throwable`.**
2. Vì sao `<E extends Exception> void run(E e) throws E` hợp lệ? **Vì `E` chắc chắn thuộc nhánh `Throwable`, và thân phương thức có thể ném chính đối tượng `e`.**
3. `throws E` có cho phép `catch (E e)` không? **Không.** Hai vị trí tuân theo quy tắc cú pháp/kiểu khác nhau.
4. Có thể khai báo `class Failure<T> extends Exception` không? **Không.** Generic class không được kế thừa `Throwable` trực tiếp hoặc gián tiếp.
5. Generic throws có loại bỏ nghĩa vụ xử lý checked exception không? **Không.** Trong cách dùng đúng, compiler vẫn kiểm tra checked exception sau khi xác định kiểu thích hợp tại call site.

## Tài liệu tham khảo

- [JLS Java SE 17 §8.4.6 — Method Throws](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.6): cho phép type variable trong `throws` nếu là subtype của `Throwable`.
- [JLS Java SE 17 §14.20 — The try Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20): cấm type variable làm kiểu của `catch`.
- [JLS Java SE 17 §18 — Type Inference](https://docs.oracle.com/javase/specs/jls/se17/html/jls-18.html): quy tắc suy luận, gồm `throws` bound và việc chọn `RuntimeException` khi thích hợp.
- [Oracle Java Tutorials — Restrictions on Generics](https://docs.oracle.com/javase/tutorial/java/generics/restrictions.html): không cho generic class kế thừa `Throwable`; minh họa `throws T` hợp lệ.
