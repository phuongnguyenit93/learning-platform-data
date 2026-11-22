# Không khai báo lớp generic kế thừa `Throwable` trong Java

## Mục tiêu học tập

Trong Java, một lớp có thể kế thừa `Exception`, `RuntimeException` hoặc `Error` để biểu diễn lỗi. Nhưng **lớp generic không được là lớp con trực tiếp hoặc gián tiếp của `java.lang.Throwable`**. Điều đó có nghĩa những ý tưởng như `class ProcessingException<T> extends Exception` hay `class Failure<T> extends RuntimeException` đều bị Java compiler từ chối.

Đây là một giới hạn của ngôn ngữ, không phải chuyện “chưa biết viết đúng cú pháp”. Type erasure khiến đối số kiểu generic không được runtime phân biệt như những loại exception khác nhau để thực hiện cơ chế `catch`.

Sau bài này, bạn có thể:

- Nhận ra những khai báo exception generic **không hợp lệ**, kể cả đường kế thừa gián tiếp từ `Throwable`.
- Hiểu vai trò của **type erasure** và cơ chế nhận diện ngoại lệ tại runtime.
- Phân biệt **generic exception class bị cấm** với **generic method khai báo `throws E` vẫn hợp lệ**.
- Viết `<E extends Exception> void propagate(E error) throws E` một cách đúng đắn.
- Giải thích vì sao không thể dùng tham số kiểu `E` làm kiểu của biến `catch (E ex)`, dù `E extends Exception`.
- Thiết kế phương án thay thế: exception **không generic** có thuộc tính typed, dùng **generic data holder** độc lập với `Throwable`, hoặc method/functional interface generic có exception type parameter.
- Đọc cảnh báo/lỗi từ `javac`, phân biệt checked và unchecked exception, và tránh suy luận sai về JVM.

Các chương trình Java 17+ trong bài đã được biên dịch và chạy thử. Các đoạn được đánh dấu **không hợp lệ** là mẫu cố ý gây lỗi compiler, không phải tệp phải chạy thành công.

## 1. Quy tắc chính xác của Java

Quy tắc quan trọng là:

> Một lớp generic không thể là lớp con của `Throwable`, dù kế thừa trực tiếp hay qua những lớp ở giữa.

Những kiểu sau đều không hợp lệ:

```java
// KHÔNG BIÊN DỊCH:
class GenericChecked<T> extends Exception {}

class GenericUnchecked<T> extends RuntimeException {}

class GenericError<T> extends Error {}

class PlainProblem extends Exception {}
class GenericIndirect<T> extends PlainProblem {}
```

Lớp `PlainProblem` ở ví dụ là một exception bình thường và **được phép**. Lỗi nằm ở `GenericIndirect<T>`: vì nó có tham số kiểu `T` và kế thừa từ `PlainProblem`, vốn là subclass của `Exception` → `Throwable`.

Java cũng không cho phép biến cách viết thành hợp lệ bằng cách thay từ `Exception` sang `RuntimeException`:

- `Exception` là subclass của `Throwable`.
- `RuntimeException` là subclass của `Exception`.
- `Error` là subclass của `Throwable`.
- Mọi subclass của các kiểu trên cuối cùng đều là subclass của `Throwable`.

Lệnh `javac` trên những trường hợp này báo lỗi **`a generic class may not extend java.lang.Throwable`**. Java không cung cấp ngoại lệ đặc biệt cho “unchecked exception generic”; cả checked, runtime exception và error đều chịu cùng giới hạn lớp generic.

## 2. Ba khái niệm dễ bị nhầm

| Cách viết | Hợp lệ? | Giải thích |
| --- | --- | --- |
| `class ParseException extends Exception` | Có | Exception class không generic |
| `class ParseException<T> extends Exception` | **Không** | Generic class là subclass của `Throwable` |
| `class ParseException<T> extends RuntimeException` | **Không** | `RuntimeException` vẫn nằm dưới `Throwable` |
| `class Child<T> extends ParseException` | **Không** | Generic subclass kế thừa `Throwable` gián tiếp |
| `record ErrorData<T>(T value) {}` | Có | Record này **không** kế thừa `Throwable` |
| `interface Result<T> {}` | Có | Interface generic bình thường, không phải exception class |
| `<E extends Exception> void run(E e) throws E` | Có | Generic **method** dùng type variable trong `throws` |
| `<E extends Exception> void run(E e) { catch (E x) {} }` | **Không** | Type variable không được làm kiểu catch parameter |
| `class ParseException extends Exception` có generic method | Có | **Class** không generic; chỉ có method generic |
| Constructor `<T> ParseException(T data)` trong exception không generic | Có | Generic constructor không biến lớp thành generic class |

Tóm lại: **cái bị cấm là sự kết hợp “lớp có type parameter” và “là subclass của Throwable”**. Java vẫn cho phép generics xuất hiện ở nhiều nơi liên quan đến xử lý lỗi, miễn không vi phạm quy tắc đó.

## 3. Tại sao Java cấm generic exception class?

Java generics chủ yếu được triển khai bằng **type erasure (xóa kiểu)**: những cách tham số hóa của cùng một generic class, chẳng hạn `Box<String>` và `Box<Integer>`, không tạo ra hai runtime class riêng theo từng đối số kiểu.

Trong khi đó, exception handling của JVM dựa vào **runtime class của đối tượng được ném** và khả năng khớp với loại exception trong bảng exception handler. Hãy tưởng tượng cú pháp sau được cho phép:

```java
// GIẢ ĐỊNH: Java thực tế KHÔNG cho khai báo kiểu này.
class Problem<T> extends Exception {}

// GIẢ ĐỊNH tiếp, nếu hai biến thể có thể được ném:
// catch (Problem<String> ex) { ... }
// catch (Problem<Integer> ex) { ... }
```

Ở mã nguồn, `Problem<String>` và `Problem<Integer>` có type arguments khác nhau. Nhưng nếu Java xử lý chúng theo cơ chế erasure thông thường, runtime class vẫn chỉ là `Problem`, không phải hai class khác nhau với type arguments có thể phân biệt ở JVM.

Vì vậy một cơ chế `catch` phân nhánh theo `<String>` và `<Integer>` **không thể dựa vào generic arguments bị xóa**. Ngôn ngữ giải quyết triệt để vấn đề ở cấp khai báo: **không cho định nghĩa generic class kế thừa `Throwable`**.

### Giới hạn của cách giải thích

Đừng hiểu sai thành “JVM không thể chứa một đối tượng exception có dữ liệu generic”. Một exception **không generic** vẫn có thể giữ các đối tượng kiểu khác nhau trong field, hoặc tham chiếu tới một **generic data holder**. Điều Java cấm là chính **lớp Throwable-subclass** có danh sách type parameters.

Đồng thời, đây là **quy tắc biên dịch của Java**; việc đọc bytecode thủ công hoặc nhìn metadata runtime không biến những khai báo source không hợp lệ thành hợp lệ. Không nên tìm một “mẹo cast” để cố qua `javac`: phương án đúng là thiết kế API khác.

## 4. Thử compiler: năm lỗi được tạo có chủ đích

Tạo tệp **`InvalidGenericExceptions.java`** sau để **quan sát lỗi**, không phải chạy:

```java
class PlainProblem extends Exception {}

class GenericCheckedProblem<T> extends Exception {}

class GenericRuntimeProblem<T> extends RuntimeException {}

class GenericIndirectProblem<T> extends PlainProblem {}

class GenericErrorProblem<T> extends Error {}

class CatchProblem {
    static <E extends Exception> void catchTypeVariable(E error) {
        try {
            throw error;
        } catch (E caught) {
            System.out.println(caught);
        }
    }
}
```

Chạy:

```bash
javac InvalidGenericExceptions.java
```

**Các chẩn đoán chính đã được kiểm chứng trên Java compiler:**

```text
error: a generic class may not extend java.lang.Throwable
error: a generic class may not extend java.lang.Throwable
error: a generic class may not extend java.lang.Throwable
error: a generic class may not extend java.lang.Throwable
error: unexpected type
  required: class
  found:    type parameter E
5 errors
```

Thứ tự ví dụ tương ứng bốn khai báo lớp generic và một `catch (E caught)` ở cuối. Đường tệp, số dòng và chú thích chi tiết của compiler có thể khác tùy phiên bản JDK; phần bản chất là:

1. `GenericCheckedProblem<T>`: generic + `Exception`.
2. `GenericRuntimeProblem<T>`: generic + `RuntimeException`.
3. `GenericIndirectProblem<T>`: generic + `PlainProblem` → `Exception`.
4. `GenericErrorProblem<T>`: generic + `Error`.
5. `catch (E caught)`: `E` là type parameter, không phải một class được phép dùng trong catch clause.

**Quan trọng:** `PlainProblem extends Exception` là khai báo hợp lệ, bản thân nó không phải nguyên nhân của một trong năm lỗi.

### Vì sao `catch (E e)` bị từ chối?

`E extends Exception` nói rằng `E` được giới hạn bởi `Exception`; nó **không** biến `E` thành một class cụ thể như `IOException.class` mà runtime catch handler có thể dùng theo ngữ nghĩa Java source.

Một catch clause yêu cầu **kiểu exception class thích hợp**, không cho phép viết một type variable làm kiểu catch parameter. Nếu cần bắt ngoại lệ bên trong generic method, có thể bắt một exception class phù hợp, hoặc thiết kế generic method để **chuyển tiếp** exception qua `throws E`, như phần tiếp theo.

## 5. Generic `throws E` là hợp lệ

Đây là điểm dễ gây nhầm lẫn nhất của bài.

**Không được viết generic exception class:**

```java
// Không hợp lệ:
class MyException<T> extends Exception {}
```

**Nhưng được viết generic method có type variable trong `throws`:**

```java
static <E extends Exception> void propagate(E error) throws E {
    throw error;
}
```

`E` ở đây là **type parameter của phương thức**, được ràng buộc bởi `Exception`. Method nhận một object exception có runtime class thật, rồi ném **chính object exception đó** bằng `throw error`. Nó không tạo một lớp exception generic mới.

Ví dụ ý tưởng sử dụng:

```java
try {
    propagate(new java.io.IOException("disk offline"));
} catch (java.io.IOException ex) {
    System.out.println(ex.getMessage());
}
```

Khi gọi `propagate` với `IOException`, compiler có thể duy trì thông tin về checked exception đó cho caller. `catch (IOException ex)` sử dụng một **exception class thật**, hợp lệ; nó không phải `catch (E ex)`.

Quy tắc áp dụng rộng hơn: tham số kiểu trong `throws E` có thể dùng khi `E` được ràng buộc thích hợp bởi `Throwable` hoặc subclass phù hợp, ví dụ `<E extends Exception>`. Việc ném và bắt các object thực ở runtime vẫn tuân thủ phân cấp `Throwable`.

## 6. Chương trình Java 17: generic method chuyển tiếp checked exception

Tạo tệp **`ExceptionGenericsDemo.java`**:

```java
import java.io.IOException;

public class ExceptionGenericsDemo {
    static final class DataException extends Exception {
        private static final long serialVersionUID = 1L;
        private final String field;

        DataException(String field, String message, Throwable cause) {
            super(message, cause);
            this.field = field;
        }

        String field() { return field; }
    }

    @FunctionalInterface
    interface ThrowingSupplier<T, E extends Exception> {
        T get() throws E;
    }

    static <T, E extends Exception> T execute(ThrowingSupplier<T, E> work)
            throws E {
        return work.get();
    }

    static <E extends Exception> void propagate(E error) throws E {
        throw error;
    }

    static int parseAge(String input) throws DataException {
        try {
            int age = Integer.parseInt(input);
            if (age < 0) throw new NumberFormatException("negative");
            return age;
        } catch (NumberFormatException ex) {
            throw new DataException("age", "Invalid age: " + input, ex);
        }
    }

    public static void main(String[] args) {
        try {
            int age = execute(() -> parseAge("21"));
            System.out.println("age: " + age);
        } catch (DataException ex) {
            System.out.println("unexpected: " + ex.getMessage());
        }

        try {
            execute(() -> parseAge("bad"));
        } catch (DataException ex) {
            System.out.println("checked: " + ex.field()
                    + " / " + ex.getMessage());
            System.out.println("cause: "
                    + ex.getCause().getClass().getSimpleName());
        }

        try {
            propagate(new IOException("disk offline"));
        } catch (IOException ex) {
            System.out.println("propagated: " + ex.getMessage());
        }
    }
}
```

Lưu file theo đúng tên class public rồi chạy:

```bash
javac -Xlint:all ExceptionGenericsDemo.java
java ExceptionGenericsDemo
```

**Stdout đã kiểm chứng:**

```text
age: 21
checked: age / Invalid age: bad
cause: NumberFormatException
propagated: disk offline
```

Chương trình này đã biên dịch thành công với `-Xlint:all` **không phát cảnh báo** trong môi trường Java 17 được dùng kiểm thử.

### Giải thích cấu trúc

**`DataException extends Exception` không generic.** Đây là checked exception class bình thường, có field `String field` để mô tả vị trí dữ liệu lỗi. `serialVersionUID` được khai báo vì exception có thể tuần tự hóa theo `Serializable`, giúp ví dụ không phát cảnh báo `[serial]` khi bật `-Xlint:all`.

**`ThrowingSupplier<T, E extends Exception>` là interface generic hợp lệ.** Nó không kế thừa `Throwable`. Tham số kiểu `T` biểu diễn kết quả và `E` biểu diễn loại checked exception mà lời gọi có thể ném.

**`execute(ThrowingSupplier<T,E>) throws E` là method generic hợp lệ.** Compiler có thể suy luận `T` từ kiểu kết quả và `E` từ hợp đồng checked exception của callback. Thân method gọi `work.get()` rồi chuyển tiếp lỗi, không bọc exception trong một generic subclass.

**`propagate(E error) throws E` ném một object exception được cung cấp.** Với `IOException`, caller có thể bắt loại exception đó theo class thật. Không có constructor của một exception generic tại đây.

**`parseAge` chuyển một lỗi parse thành `DataException`.** Nó bảo toàn nguyên nhân `NumberFormatException` qua constructor `super(message, cause)`. Đây là một mẫu checked exception thông thường, không cần khai báo `DataException<T>`.

### Checked và unchecked trong ví dụ

`DataException` và `IOException` là checked exceptions: caller phải bắt hoặc khai báo `throws` phù hợp. `NumberFormatException` là unchecked exception (con của `RuntimeException`); ở đây nó được bắt và bọc thành `DataException` để cung cấp hợp đồng rõ ràng cho API parse.

Giới hạn generic class kế thừa `Throwable` áp dụng cho **cả** `RuntimeException` và `Error`; không có chuyện unchecked thì được khai báo generic exception class.

## 7. Vì sao generic interface mang exception type argument là phương án tốt?

Một chức năng xử lý nhiều loại lỗi thường cần:

- **Kiểu kết quả**: `T`.
- **Kiểu checked exception có thể ném**: `E`.
- Một cách tái sử dụng logic mà không phải bắt mọi exception thành `Exception` hoặc `RuntimeException`.

Bạn có thể định nghĩa:

```java
@FunctionalInterface
interface ThrowingTask<T, E extends Exception> {
    T run() throws E;
}
```

Đây là **interface generic**, không phải generic exception class; hoàn toàn hợp lệ. Khi viết:

```java
static <T, E extends Exception> T runTask(ThrowingTask<T, E> task)
        throws E {
    return task.run();
}
```

thông tin generic giúp compiler áp dụng checked-exception contract cho caller. Không cần tạo `TaskException<T>`.

**Nhưng hãy hiểu giới hạn:** đây không phải cơ chế catch theo type argument. Một method nhận `ThrowingTask<String, IOException>` vẫn ném object runtime `IOException`; caller xử lý bằng `catch(IOException ex)` theo class thật, không có handler cho “`E` của callback”.

Mô hình này hữu ích khi viết những API hỗ trợ callback I/O, parsing, file operations hoặc checked exception adapters. Nếu API cần thêm context nghiệp vụ, hãy giữ context ở một **non-generic exception class** hoặc trong một **generic result/data class** riêng.

## 8. Thiết kế thay thế: exception không generic, dữ liệu có thể generic

Bài toán: bạn muốn lỗi xử lý một bản ghi chứa thông tin có kiểu riêng — chẳng hạn số trạng thái HTTP, mã lỗi, đối tượng payload. Không nên tạo `OperationException<T> extends Exception`.

Thay vào đó:

1. Lớp exception **không generic** mô tả danh tính lỗi và những field ổn định.
2. Một record/class **generic độc lập với Throwable** có thể biểu diễn dữ liệu thuộc nghiệp vụ.
3. Generic method có thể nhận `Class<T>` để kiểm tra object khi thực sự cần lấy dữ liệu kiểu `T`.

Tạo tệp **`ExceptionContextDemo.java`**:

```java
public class ExceptionContextDemo {
    record FailureData<T>(String code, T payload) {}

    static final class OperationException extends Exception {
        private static final long serialVersionUID = 1L;
        private final String code;
        private final int status;

        OperationException(String message, String code, int status) {
            super(message);
            this.code = code;
            this.status = status;
        }

        FailureData<Integer> detail() {
            return new FailureData<>(code, status);
        }

        <T> T statusAs(Class<T> expected) {
            return expected.cast(status);
        }
    }

    static void load() throws OperationException {
        throw new OperationException("Not found", "NOT_FOUND", 404);
    }

    public static void main(String[] args) {
        try {
            load();
        } catch (OperationException ex) {
            System.out.println("error type: "
                    + ex.getClass().getSimpleName());
            System.out.println("detail: " + ex.detail());
            System.out.println("status: " + ex.statusAs(Integer.class));

            try {
                ex.statusAs(String.class);
            } catch (ClassCastException cast) {
                System.out.println("wrong status type: "
                        + cast.getClass().getSimpleName());
            }
        }
    }
}
```

Biên dịch và chạy:

```bash
javac -Xlint:all ExceptionContextDemo.java
java ExceptionContextDemo
```

**Stdout đã kiểm chứng:**

```text
error type: OperationException
detail: FailureData[code=NOT_FOUND, payload=404]
status: 404
wrong status type: ClassCastException
```

Chương trình này cũng đã qua `javac -Xlint:all` **không cảnh báo**.

### Vì sao hợp lệ?

`OperationException` không có type parameter trên class declaration, vì thế được phép `extends Exception`.

`FailureData<T>` là **generic record thông thường**. Nó không là subclass của `Throwable`; việc record chứa một số trạng thái và mã lỗi là dữ liệu, không phải một exception có kiểu generic.

`detail(): FailureData<Integer>` chỉ là **kiểu trả về của method** trong non-generic exception class. Method trả một generic object thông thường; Java không cấm một Throwable-subclass có phương thức trả generic type.

`<T> T statusAs(Class<T> expected)` là **generic instance method** của một exception class không generic. Nó được phép sử dụng type parameter `T`; `Class.cast` kiểm tra việc biến số `status` (được boxing thành `Integer`) sang kiểu runtime do caller yêu cầu. Khi gọi `String.class`, cast thất bại và `ClassCastException`, chứng tỏ generic method không có quyền làm sai kiểu biến thành hợp lệ.

### Thiết kế ở mức sản phẩm

Nếu context cần lưu object bất kỳ trong exception, bạn phải quyết định vấn đề **serialization**, giới hạn kiểu, quyền sở hữu và bảo mật thông tin. Mọi `Throwable` đều có liên quan tới serialization; một field tham chiếu tới payload không serializable có thể khiến quá trình serialize exception gặp vấn đề. Ví dụ ở đây lưu riêng `String` và `int` trong exception, còn `FailureData<Integer>` được **tạo khi cần** thay vì lưu một object generic không rõ khả năng serialize.

Trong thực tế, nên ưu tiên một exception class có error code, message, cause và các thuộc tính domain cần thiết; dùng một generic result/data type riêng nếu cần mang kết quả hoặc lỗi theo kiểu tường minh mà không dựa vào exception dispatch.

## 9. Generic constructor trong exception không generic vẫn hợp lệ

Một trường hợp nữa chứng minh giới hạn chỉ áp dụng ở **class declaration**.

Tạo tệp **`GenericConstructorExample.java`**:

```java
public class GenericConstructorExample {
    static final class ReportException extends Exception {
        private static final long serialVersionUID = 1L;

        <T> ReportException(T value) {
            super("failure: " + value);
        }
    }

    public static void main(String[] args) {
        try {
            throw new ReportException(42);
        } catch (ReportException ex) {
            System.out.println(ex.getMessage());
        }
    }
}
```

Chạy:

```bash
javac -Xlint:all GenericConstructorExample.java
java GenericConstructorExample
```

Stdout đã xác minh:

```text
failure: 42
```

Ở đây `<T>` thuộc **constructor**, không phải lớp `ReportException`. Một instance `new ReportException(42)` vẫn thuộc class runtime `ReportException` bình thường. Constructor chỉ dùng `T` để nhận giá trị một cách tổng quát và tạo message, không giữ “`ReportException<Integer>`” như kiểu exception tại runtime.

Có thể chọn cách viết constructor đơn giản nhận `Object` nếu không cần generic-specific inference/constraints; generic constructor không tự mang lại type safety mạnh hơn khi đối số chỉ được chuyển thành chuỗi.

## 10. Ranh giới của `throw`, `throws E` và `catch` khi exception class không generic

Lớp exception **không generic** vẫn có thể xuất hiện trong một API dùng Generics:

```java
static <E extends Exception> void relay(E failure) throws E {
    throw failure;
}
```

Đây là **method minh họa** cần đặt trong class. `throw failure` ném một **object exception hiện có**; `throws E` mô tả checked-exception contract qua type variable của **method**, hoàn toàn không khai báo subclass generic của `Throwable`. Caller có thể bắt một class thật, ví dụ `catch (IOException ex)` trong ngữ cảnh khai báo/call phù hợp. Không thể đặt `catch (E ex)`, vì catch parameter phải có exception class hợp lệ chứ không phải type variable.

Tóm tắt chính xác:

| Thiết kế | Hợp lệ? | Vì sao |
|---|---|---|
| `class Failure extends Exception` | Có | Lớp exception không generic |
| `class Failure<T> extends Exception` | Không | Generic subclass của Throwable |
| Method `<E extends Exception> ... throws E` | Có | Generic contract ở method, không ở exception class |
| `catch (E ex)` | Không | Handler không thể định danh bằng type variable |
| `new E()` | Không | Type variable không cung cấp constructor |

**Ranh giới bài này:** giới hạn quyết định **class exception được khai báo thế nào**. Những vấn đề nâng cao như cách JVM chọn catch handler, `Class<E>.isInstance`, precise rethrow và type inference trong `throws E` thuộc hướng phân tích riêng, không thể “sửa” bằng cách làm generic exception class.

## 11. Đọc bytecode với `javap`: generic method vẫn erased

Sau khi biên dịch `ExceptionGenericsDemo.java`, chạy:

```bash
javap -s -p ExceptionGenericsDemo
javap -s -p 'ExceptionGenericsDemo$ThrowingSupplier'
```

Trích kết quả **đã kiểm chứng**:

```text
static <T, E extends java.lang.Exception> T execute(
    ExceptionGenericsDemo$ThrowingSupplier<T, E>) throws E;
  descriptor: (LExceptionGenericsDemo$ThrowingSupplier;)Ljava/lang/Object;

static <E extends java.lang.Exception> void propagate(E) throws E;
  descriptor: (Ljava/lang/Exception;)V
```

Và từ interface:

```text
interface ExceptionGenericsDemo$ThrowingSupplier<T, E extends java.lang.Exception> {
  public abstract T get() throws E;
    descriptor: ()Ljava/lang/Object;
}
```

Những dòng hiển thị `<T, E extends Exception>` đến từ generic metadata mà `javap` có thể trình bày. Nhưng JVM descriptors dùng erasure:

- `T` không bound được xóa thành `Object`.
- `E extends Exception` trong **vị trí tham số kiểu của phương thức** được xóa thành `Exception`.
- `ThrowingSupplier<T,E>` được biểu diễn theo runtime interface `ThrowingSupplier`, không có biến thể class riêng theo type arguments.

**Điểm cần phân biệt:** descriptor không “mang lại” generic exception class. `throws E` vẫn là khai báo checked-exception contract tại source; runtime object được ném là một exception thực như `IOException` hoặc `DataException`.

Với `javap -v`, bạn có thể xem thêm generic `Signature` và các thuộc tính liên quan tới declared exceptions. Nhưng đừng dùng descriptor như bằng chứng rằng JVM có catch handler phân biệt `Exception<String>` và `Exception<Integer>`; những kiểu exception generic đó không tồn tại hợp lệ trong Java source.

## 12. Checked vs unchecked exception không tạo ngoại lệ cho quy tắc

| Nhóm | Ví dụ | Compile-time handling | Có được generic subclass không? |
| --- | --- | --- | --- |
| Checked exception | `Exception`, `IOException`, `DataException` | Cần catch/throws phù hợp | **Không** |
| Unchecked exception | `RuntimeException`, `IllegalArgumentException` | Không buộc catch/throws | **Không** |
| Error | `Error`, `AssertionError` | Không buộc catch/throws | **Không** |

Việc unchecked exception có thể tự lan truyền mà không phải khai báo trong `throws` **không liên quan** tới luật cấm subclass generic của `Throwable`.

Ví dụ:

```java
// Cả hai đều KHÔNG BIÊN DỊCH:
class RetryException<T> extends RuntimeException {}
class BrokenSystemError<T> extends Error {}
```

Chúng vẫn là generic classes nằm dưới cây kế thừa `Throwable`.

Thay thế đúng:

```java
class RetryException extends RuntimeException {
    private static final long serialVersionUID = 1L;
    RetryException(String message) { super(message); }
}
```

Nếu muốn mang thêm thông tin typed về tác vụ đang retry, có thể đưa nó vào một generic result wrapper không kế thừa `Throwable`, hoặc cung cấp field/method thích hợp với một hợp đồng runtime rõ.

## 13. Những sai lầm phổ biến

**Sai lầm 1 — “Không được generic hóa bất cứ thứ gì liên quan exception.”** Không đúng. Generic methods có `throws E`, generic functional interfaces và generic data holders đều hợp lệ. Chỉ **generic class là Throwable-subclass** bị cấm.

**Sai lầm 2 — “Thay `Exception` bằng `RuntimeException` sẽ giải quyết lỗi.”** Không đúng. `RuntimeException` vẫn là subclass của `Throwable`, nên `class X<T> extends RuntimeException` vẫn bị từ chối.

**Sai lầm 3 — “Kế thừa gián tiếp sẽ tránh được giới hạn.”** Không đúng. `class X<T> extends NonGenericException` cũng sai nếu `NonGenericException` nằm dưới `Throwable`.

**Sai lầm 4 — “`throws E` bị cấm giống `catch (E)`.”** Không đúng. Đây là hai vị trí cú pháp và hai quy tắc khác nhau. `throws E` hợp lệ khi bound phù hợp; `catch (E)` không hợp lệ.

**Sai lầm 5 — “`E extends Exception` làm E thành một class thực tại runtime.”** Không đúng. `E` vẫn là type variable. Khi gọi với `IOException`, object thật là `IOException`, nhưng `E` không trở thành class literal dùng được trong catch clause.

**Sai lầm 6 — “Cứ có `<T>` trong constructor là toàn bộ exception class generic.”** Không đúng. Constructor generic có thể nằm trong một class exception **không generic**, như `ReportException` ở mục 9.

**Sai lầm 7 — “Cast hoặc reflection có thể ép `GenericException<T>` thành hợp lệ.”** Không đúng ở Java source. Runtime reflection không thay đổi quy tắc khai báo class do compiler áp dụng.

**Sai lầm 8 — “Một generic result record là exception.”** `FailureData<T>` chỉ là object dữ liệu. Nó không tự làm thay `try/catch`; muốn dùng exception flow thì ném một non-generic Throwable object hoặc dùng một API trả result rõ ràng.

**Sai lầm 9 — “Exception có field Object chứa gì cũng an toàn.”** Nếu dữ liệu đến từ nguồn không kiểm soát, vẫn cần validation/type token. Ngoài ra, `Throwable` liên quan tới serialization, nên field chứa object không serializable phải được thiết kế cẩn thận.

**Sai lầm 10 — “Vì type erasure, generic method có `throws E` không còn ích gì.”** Không đúng. Compiler vẫn kiểm tra contract generic của callback/caller, nên generic throws rất hữu ích dù bytecode dùng kiểu erased.

## 14. Khi thiết kế API thực tế, chọn cách nào?

### Bạn muốn phân biệt các loại lỗi nghiệp vụ bằng `catch`

Dùng **non-generic exception classes** thích hợp như `ValidationException`, `DataException`, `NotFoundException`. Mỗi loại có runtime class riêng, phù hợp với cách JVM dispatch exception handlers.

### Bạn muốn một exception có mã lỗi và context

Thêm field/method vào **non-generic exception class**. Giữ nguyên nhân bằng `Throwable cause`, ví dụ `super(message, cause)`. Nếu payload nhiều kiểu, xem xét serialized form, `Class<T>` token hoặc validator rõ ràng.

### Bạn muốn hàm hỗ trợ nhiều loại checked exception

Dùng method `<T, E extends Exception> T execute(ThrowingSupplier<T,E> action) throws E`. Điều này giữ được thông tin checked exception ở source mà không cần tạo generic Throwable subclass.

### Bạn muốn kiểu dữ liệu kết quả/lỗi ở compile time

Dùng **generic result wrapper** độc lập với Throwable, ví dụ một `record Result<T>(T value, String errorCode)`, hoặc một sealed hierarchy riêng để biểu diễn trạng thái thành công/thất bại. Cách này phù hợp khi lỗi là dữ liệu do caller kiểm tra thay vì exception được ném.

### Bạn muốn truyền exception vào một utility

Chấp nhận một biến `E extends Exception` hoặc một `Supplier<? extends E>` phù hợp; ném exception object thực. Không cố tự tạo `new E()` hoặc `catch (E)`.

## 15. Bài tập có đáp án

### Bài 1 — Bốn khai báo

Xét:

```java
class A extends Exception {}
class B<T> extends Exception {}
class C<T> extends RuntimeException {}
class D<T> extends A {}
```

**Câu hỏi:** những lớp nào hợp lệ?

**Đáp án:** chỉ `A` hợp lệ. `B`, `C` generic trực tiếp dưới `Throwable`; `D` generic gián tiếp dưới `Throwable`.

### Bài 2 — Generic method và generic class

```java
static <E extends Exception> void send(E error) throws E {
    throw error;
}
```

**Câu hỏi:** vì sao method này hợp lệ mà `class EBox<E> extends Exception` không hợp lệ?

**Đáp án:** type variable `E` thuộc generic method để mô tả kiểu object exception được truyền và ném; method không định nghĩa một generic class nằm dưới `Throwable`. `EBox<E>` thì định nghĩa trực tiếp một generic exception class, bị cấm.

### Bài 3 — Catch theo `E`

Cho `<E extends IOException> void handle(E e)`, có được dùng `catch(E ex)` không?

**Đáp án:** không. Type variable dù có bound cụ thể vẫn không là một catchable exception class trong catch parameter. Có thể bắt `IOException` nếu phù hợp với vùng try và các quy tắc checked exception; hoặc chuyển tiếp bằng `throws E`.

### Bài 4 — Chọn thiết kế

Một ứng dụng muốn báo lỗi `NotFound` kèm mã trạng thái `404` và metadata chi tiết kiểu riêng.

**Đáp án định hướng:** tạo `NotFoundException extends Exception`/ `RuntimeException` **không generic**, lưu `code`, `status`, `message`, `cause` phù hợp; nếu cần một cấu trúc dữ liệu typed, tạo `FailureData<Integer>` riêng. Không viết `NotFoundException<Integer> extends Exception`.

### Bài 5 — Đọc bytecode

Method `<E extends Exception> void propagate(E error) throws E` có erased parameter type nào?

**Đáp án:** `Exception`, vì giới hạn trên của `E` là `Exception`; JVM descriptor tiêu biểu `(Ljava/lang/Exception;)V`.

### Bài 6 — Constructor có `<T>`

```java
class ReportException extends Exception {
    <T> ReportException(T value) { super(String.valueOf(value)); }
}
```

**Câu hỏi:** có bị cấm bởi quy tắc generic Throwable subclass không?

**Đáp án:** không. Class `ReportException` không generic; constructor mới là thành viên generic. Đừng hiểu việc constructor có `T` là JVM tạo `ReportException<String>` class riêng.

### Bài 7 — Checked exception contract

Vì sao `ThrowingSupplier<T,E extends Exception>` có ích?

**Đáp án:** nó cho phép mô tả đồng thời kiểu kết quả `T` và loại checked exception `E` trong lời gọi, giúp caller bắt hoặc khai báo loại lỗi cụ thể khi compiler suy luận được `E`.

### Bài 8 — Chuyển exception thành dữ liệu

Nếu API không cần `throw/catch` mà muốn caller kiểm tra có lỗi hay không, cách nào phù hợp?

**Đáp án:** một generic result type hoặc sealed result hierarchy **không** kế thừa `Throwable`. Generic classes như `Result<T>` có thể giữ typed payload mà không vi phạm quy tắc exception hierarchy.

## 16. Checklist ghi nhớ

Khi thiết kế exception hoặc generic utility trong Java:

- [ ] Nếu class có `<T>`, nó **không** phải subclass trực tiếp/gián tiếp của `Throwable`.
- [ ] Không viết `class X<T> extends Exception`, `RuntimeException` hay `Error`.
- [ ] Nếu cần catch theo loại lỗi, dùng exception **class cụ thể không generic**.
- [ ] Phân biệt `catch(E)` bị cấm với `throws E` có thể hợp lệ.
- [ ] Nếu `throw error` dùng type variable, bound và khai báo `throws` phù hợp.
- [ ] Nếu cần typed callback, dùng generic interface `ThrowingSupplier<T,E>`.
- [ ] Nếu cần typed context, dùng generic data class/record độc lập với `Throwable`.
- [ ] Nếu lưu dữ liệu trong exception, cân nhắc `cause`, serialization và kiểm tra kiểu runtime.
- [ ] Nếu dùng generic method bên trong exception class, bảo đảm **class vẫn không generic**.
- [ ] Kiểm tra ví dụ bằng `javac`, đối chiếu output đúng và không cố né lỗi compiler bằng unchecked cast.

## Kết luận

**Java không cho khai báo một generic class kế thừa `Throwable` dù trực tiếp hay gián tiếp**, nên `class MyException<T> extends Exception` và `class MyRuntimeException<T> extends RuntimeException` đều sai. Đây là giới hạn của ngôn ngữ liên quan type erasure và cơ chế nhận diện exception theo runtime class.

Tuy vậy, **generics vẫn dùng được trong thiết kế xử lý lỗi**: generic methods với `throws E`, generic callback interfaces, generic constructors trong non-generic exceptions và các generic data holders đều có chỗ đứng. Hãy giữ exception classes không generic để `throw/catch` hoạt động rõ ràng, và đặt type parameters ở các API/kiểu dữ liệu thực sự cần chúng.
