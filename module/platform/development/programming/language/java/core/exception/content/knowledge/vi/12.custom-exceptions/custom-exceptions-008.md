# Giới hạn generic: lớp con `Throwable` không được có tham số kiểu trong Java

Java cho phép lập trình generic để viết mã dùng được với nhiều kiểu dữ liệu, nhưng đặt ra một giới hạn đặc biệt với hệ phân cấp ngoại lệ: **một lớp generic không được là lớp con trực tiếp hoặc gián tiếp của `java.lang.Throwable`**. Vì vậy, các khai báo như `class MyException<T> extends Exception`, `class MyRuntimeException<T> extends RuntimeException` và `class MyError<T> extends Error` đều **không biên dịch**.

Đây là một quy tắc của **Java Language Specification (JLS) §8.1.2**, không phải lỗi thiếu import hay vấn đề riêng của một phiên bản `javac`. Cơ chế bắt ngoại lệ trong Java/JVM dựa trên **lớp ngoại lệ lúc chạy**, không dựa vào tham số generic `<T>` vốn bị xóa trong quá trình biên dịch (*type erasure*).

Quan trọng không kém: **điều bị cấm là lớp ngoại lệ có tham số kiểu**, chứ không phải mọi cách sử dụng generics liên quan đến ngoại lệ. Một lớp ngoại lệ **không generic** vẫn có thể chứa trường `List<String>`; phương thức generic có thể khai báo `throws E` với `E extends Throwable`; lớp `Result<T, E>` có thể mang theo một ngoại lệ. Nhưng tham số kiểu `E` không được đặt trực tiếp làm kiểu trong `catch (E ex)`.

Bài này trình bày nguyên nhân, cú pháp đúng/sai, các ngoại lệ thiết kế thường gặp, cách giữ metadata có kiểu, generic `throws`, lỗi khi sử dụng `catch` và các phương án thay thế có thể áp dụng trong Java 17+.

## 1. Quy tắc chính xác trong JLS §8.1.2

JLS quy định rằng một **generic class** không được là **direct or indirect subclass** của `Throwable`. Một lớp là generic khi **bản thân khai báo lớp** có phần khai báo tham số kiểu, ví dụ `class Box<T>` hoặc `class Pair<K, V>`.

Hai hình thức sau **đều bị cấm**:

```java
// CỐ Ý KHÔNG BIÊN DỊCH:
class TypedException<T> extends Exception {
    TypedException(String message) {
        super(message);
    }
}

class TypedRuntimeFailure<T> extends RuntimeException {
    TypedRuntimeFailure(String message) {
        super(message);
    }
}
```

Ở cả hai lớp, bản thân khai báo lớp có `<T>` và lớp cha nằm trên nhánh `Throwable`. `javac` thường báo lỗi có ý nghĩa như:

```text
a generic class may not extend java.lang.Throwable
```

Thông báo có thể thay đổi theo JDK, nhưng **nguyên nhân compile-time không thay đổi**.

Giới hạn không chỉ áp dụng với `Exception`:

| Khai báo | Kết quả | Lý do |
| --- | --- | --- |
| `class GenericFailure<T> extends Throwable` | Không hợp lệ | Generic class trực tiếp kế thừa `Throwable` |
| `class GenericFailure<T> extends Exception` | Không hợp lệ | Generic class gián tiếp kế thừa `Throwable` |
| `class GenericFailure<T> extends RuntimeException` | Không hợp lệ | Runtime exception vẫn là `Throwable` |
| `class GenericFailure<T> extends Error` | Không hợp lệ | `Error` là nhánh con của `Throwable` |
| `class InputFailure extends Exception` | Hợp lệ | Lớp ngoại lệ **không có tham số kiểu** |
| `class Box<T>` | Hợp lệ | Đây không phải lớp con của `Throwable` |
| `class Outcome<T, E extends Exception>` | Hợp lệ khi không kế thừa `Throwable` | Lớp generic chứa/chuyển một ngoại lệ, không phải chính ngoại lệ |

**Lưu ý:** một lớp ngoại lệ có thể dùng nhiều kiểu generic trong thân mà vẫn **không phải lớp generic**. Tiêu chí là khai báo lớp đó có danh sách tham số kiểu `<...>` hay không và có kế thừa `Throwable` hay không.

## 2. “Gián tiếp” có nghĩa là gì?

Giả sử đã có một lớp ngoại lệ không generic:

```java
class ApplicationFailure extends RuntimeException {
    ApplicationFailure(String message) {
        super(message);
    }
}
```

Lớp này hợp lệ. Nhưng cách kế thừa sau **không hợp lệ**:

```java
// CỐ Ý KHÔNG BIÊN DỊCH:
class GenericServiceFailure<T> extends ApplicationFailure {
    GenericServiceFailure(String message) {
        super(message);
    }
}
```

Chuỗi kế thừa thực chất là:

```text
GenericServiceFailure<T>
        |
        extends
        v
ApplicationFailure
        |
        extends
        v
RuntimeException
        |
        extends
        v
Exception
        |
        extends
        v
Throwable
```

Mặc dù `GenericServiceFailure<T>` **không viết trực tiếp** `extends Throwable`, nó vẫn là một lớp con gián tiếp. Do đó giới hạn vẫn áp dụng.

Không thể “né” quy tắc bằng cách đặt thêm lớp ngoại lệ trung gian không generic. Điều kiện là **toàn bộ quan hệ kế thừa của chính lớp generic**, không chỉ tên lớp cha xuất hiện ngay sau `extends`.

## 3. Vì sao Java cấm generic exception class?

### 3.1. Generics bị xóa tham số kiểu ở runtime

Java chủ yếu hiện thực generics theo cơ chế **type erasure**. Ví dụ:

```java
java.util.List<String> names = new java.util.ArrayList<>();
java.util.List<Integer> numbers = new java.util.ArrayList<>();

System.out.println(names.getClass() == numbers.getClass());
```

Đây là đoạn mã chạy được khi đặt trong phương thức. Kết quả là `true` vì cả hai đối tượng đều có lớp runtime `ArrayList`; tham số kiểu `String` và `Integer` không tạo ra hai lớp Java runtime riêng biệt.

Đối với generic exception *giả định*:

```java
// CHỈ LÀ GIẢ THUYẾT; GenericFailure<T> bị JLS cấm khai báo.
GenericFailure<String> a;
GenericFailure<Integer> b;
```

Nếu Java cho phép loại lớp này, hai tham số hóa sẽ không trở thành hai lớp ngoại lệ runtime riêng. Cơ chế xử lý ngoại lệ không thể dựa vào tham số generic để phân biệt chúng.

### 3.2. `catch` lựa chọn kiểu ngoại lệ theo lớp runtime

Java chọn nhánh `catch` đầu tiên tương thích với **kiểu runtime của đối tượng ném ra**. JVM sử dụng thông tin lớp trong bảng exception handler của mã bytecode; nó không có hai handler độc lập chỉ dựa vào `T = String` hay `T = Integer` của cùng một lớp generic bị erasure.

Hãy tưởng tượng mã sau nếu một lớp generic exception được cho phép:

```java
// GIẢ ĐỊNH SAI — KHÔNG THỂ BIÊN DỊCH TRONG JAVA:
try {
    throw new GenericFailure<String>();
} catch (GenericFailure<String> ex) {
    System.out.println("String");
} catch (GenericFailure<Integer> ex) {
    System.out.println("Integer");
}
```

Ví dụ trên chỉ dùng để **giải thích tính bất khả thi của thiết kế**, không phải cú pháp cần sửa vài ký tự là chạy được. Hai dạng tham số hóa sẽ có cùng lớp runtime; không thể chọn handler theo `String` hoặc `Integer` như những kiểu ngoại lệ hoàn toàn khác nhau.

JLS §8.1.2 nêu rõ nguyên nhân của giới hạn là **cơ chế `catch` của JVM chỉ hoạt động với các lớp không generic**. Đây là ràng buộc chính thức của ngôn ngữ, không đơn thuần là một lời khuyên về phong cách lập trình.

## 4. Phân biệt ba điều dễ bị đánh đồng

| Tình huống | Hợp lệ? | Giải thích |
| --- | --- | --- |
| `class Failure<T> extends Exception` | **Không** | Chính lớp exception là generic |
| `class Failure extends Exception { List<String> details; }` | **Có** | Lớp exception không generic, trường sử dụng một kiểu generic cụ thể |
| `class Holder<T> { T data; Exception failure; }` | **Có** | Lớp generic không kế thừa Throwable |
| `class Result<T, E extends Exception>` không extends Throwable | **Có** | Tham số E biểu diễn loại lỗi đi kèm, không phải loại lớp Result |
| `static <E extends Exception> void relay(E ex) throws E` | **Có** | Method generic dùng type variable trong mệnh đề throws |
| `catch (E ex)` với `E extends Exception` | **Không** | Type variable không được làm kiểu tham số catch |
| `catch (IOException | SQLException ex)` | **Có** nếu try có thể ném các loại checked này | Multi-catch liệt kê **các lớp cụ thể**, không phải type variables |
| `class Failure extends RuntimeException { <T> T detailAs(Class<T> type) ... }` | **Có** | Phương thức generic trong lớp exception không generic |

**Hai từ “generic” và “exception” xuất hiện trong cùng file không gây lỗi.** Chỉ khi khai báo vi phạm một quy tắc cụ thể của ngôn ngữ, chẳng hạn **generic subclass of Throwable** hoặc **type variable in catch**, trình biên dịch mới từ chối.

## 5. Thiết kế đúng: custom exception không generic nhưng có metadata có kiểu

Thông thường, thông tin nghiệp vụ cần mang theo ngoại lệ là một **giá trị cụ thể**: tên trường bị lỗi, danh sách vi phạm, mã lỗi hoặc ID tác vụ. Không cần biến bản thân *lớp ngoại lệ* thành generic.

Ví dụ:

```java
import java.util.List;

class ValidationFailure extends Exception {
    private final List<String> violations;

    ValidationFailure(String message, List<String> violations) {
        super(message);
        this.violations = List.copyOf(violations);
    }

    public List<String> getViolations() {
        return violations;
    }
}
```

Đây là **lớp hợp lệ**, không chứa `main()` độc lập. Lớp `ValidationFailure` không có tham số kiểu, nhưng trường `List<String>` vẫn được kiểm tra kiểu lúc biên dịch. `List.copyOf(...)` tạo bản sao không thể sửa qua các thao tác thông thường của `List`, giảm nguy cơ mã ngoài thay đổi danh sách đã gắn với ngoại lệ.

### Chương trình Java 17+ hoàn chỉnh

Lưu thành `ValidationFailureDemo.java`:

```java
import java.util.List;

public class ValidationFailureDemo {
    static final class ValidationFailure extends Exception {
        private final List<String> violations;

        ValidationFailure(String message, List<String> violations) {
            super(message);
            this.violations = List.copyOf(violations);
        }

        List<String> getViolations() {
            return violations;
        }
    }

    static <T> T requirePresent(T value, String field)
            throws ValidationFailure {
        if (value == null) {
            throw new ValidationFailure(
                    "Invalid field: " + field,
                    List.of(field + " is required"));
        }
        return value;
    }

    public static void main(String[] args) {
        try {
            System.out.println("valid="
                    + requirePresent("C-42", "customerId"));
            requirePresent(null, "customerId");
        } catch (ValidationFailure ex) {
            System.out.println("type="
                    + ex.getClass().getSimpleName());
            System.out.println("message=" + ex.getMessage());
            System.out.println("violations=" + ex.getViolations());
        }
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 ValidationFailureDemo.java
java ValidationFailureDemo
```

Kết quả:

```text
valid=C-42
type=ValidationFailure
message=Invalid field: customerId
violations=[customerId is required]
```

Phân tích:

1. `ValidationFailure` là **custom checked exception không generic**.
2. Trường `List<String>` chứa thông tin đã biết cấu trúc; không biến ngoại lệ thành `ValidationFailure<String>`.
3. Phương thức `requirePresent` **là generic** vì khai báo `<T>` và trả cùng loại T của tham số. Generic method có thể ném một loại ngoại lệ **cụ thể** `ValidationFailure`.
4. `main()` bắt loại ngoại lệ cụ thể này; đây là kiểu `catch` hợp lệ.
5. Lỗi có thông điệp và metadata riêng mà không vi phạm JLS §8.1.2.

Nếu metadata nhạy cảm, cân nhắc loại nào được phép đi vào exception/log. Một field có kiểu không có nghĩa được phép chứa mật khẩu, token hoặc thông tin cá nhân cần bảo vệ.

## 6. Phương thức generic có thể khai báo `throws E`

Mệnh đề `throws` được khai báo trên **phương thức hoặc constructor**, không phải trên bản thân lớp ngoại lệ. JLS §8.4.6 cho phép một **type variable** làm kiểu trong danh sách `throws`, với điều kiện kiểu đó là subtype của `Throwable`.

Ví dụ:

```java
static <E extends Exception> void rethrow(E failure) throws E {
    throw failure;
}
```

Đây là **phương thức minh họa**, có thể đặt trong một lớp thông thường. Nó được phép dùng `E` trong chữ ký `throws E` và trong biểu thức `throw failure;`. Tại điểm gọi, `E` được suy ra từ kiểu của đối tượng ngoại lệ.

### Chương trình Java 17+ kiểm chứng generic `throws`

Lưu thành `GenericThrowsDemo.java`:

```java
import java.io.IOException;
import java.text.ParseException;

public class GenericThrowsDemo {
    static <E extends Exception> void rethrow(E failure) throws E {
        throw failure;
    }

    static <E extends Exception> void check(
            boolean fail, E failure) throws E {
        if (fail) {
            rethrow(failure);
        }
    }

    public static void main(String[] args) {
        try {
            check(true, new IOException("disk failure"));
        } catch (IOException ex) {
            System.out.println("io=" + ex.getMessage());
        }

        try {
            check(true, new ParseException("bad token", 0));
        } catch (ParseException ex) {
            System.out.println("parse=" + ex.getMessage());
        }

        try {
            check(false, new IOException("not thrown"));
            System.out.println("success");
        } catch (IOException ex) {
            System.out.println("unreachable on this input");
        }
    }
}
```

```bash
javac -encoding UTF-8 GenericThrowsDemo.java
java GenericThrowsDemo
```

Kết quả:

```text
io=disk failure
parse=bad token
success
```

Ở đây:

- Lớp `GenericThrowsDemo` **không generic**.
- Hai phương thức có type variable `E extends Exception` nên là **generic methods**.
- `throws E` được JLS cho phép; ở các lời gọi minh họa, compiler suy ra `E` tương ứng với `IOException` hoặc `ParseException`.
- Các `catch` vẫn dùng **lớp ngoại lệ cụ thể**.
- `check(false, ...)` không ném trong lần chạy này, nhưng chữ ký vẫn mô tả khả năng ném E; đoạn `catch(IOException)` vẫn hợp lệ.

Điểm khác biệt trọng tâm: **generic method có thể truyền loại ngoại lệ qua type parameter**, trong khi **generic exception class** vẫn không được khai báo.

## 7. Tại sao `catch (E ex)` lại không hợp lệ?

JLS §14.20 đặt ra quy tắc riêng: **không được dùng type variable làm kiểu của một exception parameter** trong `catch`.

Ví dụ sau **cố ý không biên dịch**:

```java
class InvalidGenericCatch {
    static <E extends Exception> void handle(E sample) throws E {
        try {
            throw sample;
        } catch (E ex) { // Lỗi biên dịch: type variable trong catch.
            System.out.println(ex.getMessage());
        }
    }
}
```

Không phải vì `E extends Exception` là sai; chính **vị trí của E trong `catch`** bị JLS cấm. Việc dùng `throws E` ở chữ ký phương thức là hợp lệ.

Một cách xử lý hợp lệ khi thật sự muốn dùng mã chung là bắt **kiểu lớp cụ thể được thiết kế cho giao diện xử lý**:

```java
static <E extends Exception> void handle(E sample) {
    try {
        throw sample;
    } catch (Exception ex) {
        System.out.println(ex.getMessage());
    }
}
```

Đây là phương thức minh họa hợp lệ; `catch (Exception ex)` là một kiểu lớp cụ thể, không phải type variable. Dù vậy, việc bắt rộng `Exception` có thể nuốt nhiều lỗi hơn ý định. Chỉ sử dụng khi phương thức thật sự có chính sách xử lý chung; nếu cần chuyển nguyên loại `E` cho bên gọi, **cho ngoại lệ lan truyền bằng `throws E`** thường chính xác hơn.

Lưu ý rằng một nhánh `catch` kiểm tra **kiểu runtime của ngoại lệ**. Kiểu tham số là type variable không tạo ra class token đủ để JVM phân biệt những tham số generic khác nhau.

## 8. Thay thế bằng generic class *chứa* lỗi, không *là* lỗi

Một giải pháp thiết kế phổ biến là **giữ ngoại lệ thành lớp thường** và đưa generics vào một lớp mô tả kết quả, trạng thái hoặc cơ chế xử lý.

Ví dụ cấu trúc:

```java
final class Outcome<T, E extends Exception> {
    private final T value;
    private final E failure;

    Outcome(T value, E failure) {
        this.value = value;
        this.failure = failure;
    }

    T valueOrThrow() throws E {
        if (failure != null) {
            throw failure;
        }
        return value;
    }
}
```

Đây là **một lớp generic hợp lệ** vì `Outcome` không kế thừa `Throwable`. Hai type parameter mang ý nghĩa khác nhau:

- `T`: giá trị thành công;
- `E extends Exception`: loại ngoại lệ được lưu nếu thất bại.

### Chương trình Java 17+ chạy được

Lưu thành `GenericOutcomeDemo.java`:

```java
import java.io.IOException;

public class GenericOutcomeDemo {
    static final class Outcome<T, E extends Exception> {
        private final T value;
        private final E failure;

        Outcome(T value, E failure) {
            this.value = value;
            this.failure = failure;
        }

        T valueOrThrow() throws E {
            if (failure != null) {
                throw failure;
            }
            return value;
        }
    }

    public static void main(String[] args) {
        Outcome<String, IOException> good =
                new Outcome<>("READY", null);
        Outcome<String, IOException> bad =
                new Outcome<>(null, new IOException("file unavailable"));

        try {
            System.out.println("good=" + good.valueOrThrow());
            System.out.println("bad=" + bad.valueOrThrow());
        } catch (IOException ex) {
            System.out.println("caught=" + ex.getMessage());
        }
    }
}
```

```bash
javac -encoding UTF-8 GenericOutcomeDemo.java
java GenericOutcomeDemo
```

Kết quả:

```text
good=READY
caught=file unavailable
```

Với `good`, trường `failure` bằng `null` nên trả về chuỗi `READY`. Với `bad`, phương thức `valueOrThrow()` ném **chính đối tượng `IOException` đã lưu**; lệnh `println("bad=" + ...)` không được thực thi. `catch (IOException)` bắt lỗi cụ thể ở tầng gọi.

**Lưu ý về thiết kế:** lớp `Outcome` trên minh họa cơ chế generic và ngoại lệ. Một Result/Outcome production-grade nên có bất biến rõ ràng như “chỉ một trong value hoặc failure được thiết lập”, factory methods, null policy và mô hình trạng thái nhất quán. Không nên sử dụng thiết kế demo để biểu diễn mọi trường hợp dữ liệu mà không bổ sung các kiểm tra đó.

## 9. Generic methods trong một lớp ngoại lệ không generic

Một custom exception vẫn có thể sở hữu **generic method**, ví dụ để đọc metadata đã lưu qua một runtime class token.

Lưu thành `TypedDetailDemo.java`:

```java
public class TypedDetailDemo {
    static final class DomainFailure extends RuntimeException {
        private final Object detail;

        DomainFailure(String message, Object detail) {
            super(message);
            this.detail = detail;
        }

        <T> T detailAs(Class<T> type) {
            return type.cast(detail);
        }
    }

    public static void main(String[] args) {
        DomainFailure failure =
                new DomainFailure("invalid amount", Integer.valueOf(25));

        Integer amount = failure.detailAs(Integer.class);
        System.out.println("detail=" + amount);
        System.out.println("message=" + failure.getMessage());

        try {
            String wrong = failure.detailAs(String.class);
            System.out.println(wrong);
        } catch (ClassCastException ex) {
            System.out.println("wrong-type=ClassCastException");
        }
    }
}
```

```bash
javac -encoding UTF-8 TypedDetailDemo.java
java TypedDetailDemo
```

Kết quả:

```text
detail=25
message=invalid amount
wrong-type=ClassCastException
```

Lớp `DomainFailure` là một **non-generic exception class**, không có `<T>` trên khai báo lớp. Phương thức `detailAs` mới có `<T>`; nó dùng `Class<T>.cast(...)` để kiểm tra kiểu được yêu cầu khi chạy, thay vì ép kiểu mù hoặc nghĩ rằng erasure tự bảo vệ dữ liệu.

Ví dụ này minh họa tính hợp lệ của generic method, **không phải lời khuyên lưu mọi metadata của exception dưới dạng `Object`**. Trong nhiều API, thuộc tính với kiểu cụ thể như `String fieldName`, `int errorCode` hoặc `List<String> violations` dễ đọc, dễ kiểm thử và an toàn hơn.

## 10. Phân biệt generic `throws`, checked exception và `RuntimeException`

Để hiểu những giới hạn này, cần tách ba tầng quy tắc:

1. **Khai báo lớp:** generic class không được kế thừa `Throwable` trực tiếp hoặc gián tiếp (JLS §8.1.2).
2. **Khai báo phương thức:** một type variable có bound phù hợp `Throwable` được phép xuất hiện trong `throws` (JLS §8.4.6).
3. **Tham số `catch`:** type variable không được dùng làm kiểu exception parameter (JLS §14.20).

Việc một ngoại lệ là **checked** hay **unchecked** là trục quy tắc khác:

| Loại | Ví dụ | Nghĩa vụ bình thường của bên gọi |
| --- | --- | --- |
| Checked exception | `IOException`, custom `extends Exception` (không thuộc `RuntimeException`) | Bắt hoặc khai báo `throws` nếu có thể thoát ra |
| Unchecked exception | `RuntimeException` và các lớp con | Không bắt buộc khai báo `throws` |
| Unchecked error | `Error` và các lớp con | Không bắt buộc khai báo `throws`; thường không phải nhóm cần bắt để phục hồi |

**Cả checked và unchecked đều không được phép khai báo lớp ngoại lệ generic.** Viết `extends RuntimeException` không phải đường vòng để có `MyException<String>` hợp lệ.

Ngược lại, `<E extends Exception> ... throws E` là một khái niệm về **generic method và type bound**. Không cần tạo ra `Exception<E>` để thực hiện nó.

## 11. `catch` cụ thể và multi-catch vẫn dùng như bình thường

Khi có hai loại lỗi mà một quy trình cần xử lý chung, Java hỗ trợ multi-catch:

```java
try {
    readOrQuery();
} catch (java.io.IOException | java.sql.SQLException ex) {
    reportFailure(ex);
}
```

Đây là **đoạn minh họa**, giả sử `readOrQuery()` có thể ném hai checked exceptions tương ứng và `reportFailure(Exception)` đã được định nghĩa.

Các loại trong multi-catch là những **lớp ngoại lệ cụ thể**, được phân biệt tại runtime. Cú pháp này **không đòi generic exception class**. Một multi-catch duy nhất chọn và thực thi một thân xử lý cho các loại tương ứng.

Điều Java không cho phép là đặt một **type variable** thay cho tên lớp trong nhánh `catch`:

```java
// CỐ Ý KHÔNG HỢP LỆ:
catch (E ex) {
    // E extends Exception vẫn không hợp lệ ở vị trí này.
}
```

Với mã điều phối generic cần xử lý mọi `E` theo một chính sách, bạn có thể chọn bắt một lớp cha cụ thể ở tầng có trách nhiệm chung, hoặc không bắt và để `throws E` truyền lỗi cho tầng trên. Không viết `catch (T)` chỉ để làm cho mã trông “tổng quát”.

## 12. Các phương án thiết kế thay thế và khi nào dùng

| Nhu cầu thực tế | Thiết kế nên cân nhắc | Vì sao |
| --- | --- | --- |
| Một lỗi nghiệp vụ có các thuộc tính cố định | Non-generic `DomainException` với trường `String`, `int`, `enum`, `List<String>` | Giữ ngoại lệ cụ thể, thuộc tính có kiểu |
| Nhiều loại lỗi riêng biệt cần bắt riêng | Các lớp `FileFailure`, `ValidationFailure`, `ServiceFailure` không generic | `catch` theo kiểu runtime riêng |
| Muốn cùng một thuật toán chuyển tiếp nhiều loại checked exception | Generic method `<E extends Exception> ... throws E` | Giữ chính xác type bound mà không tạo generic exception |
| Muốn kết quả có giá trị hoặc lỗi có kiểu | Generic `Result<T,E>`/`Outcome<T,E>` không extends Throwable | Generics nằm ở vùng quản lý kết quả |
| Muốn chuyển lỗi giữa các tầng | Non-generic custom exception nhận `(String, Throwable)` | Giữ cause chain, tránh mất ngữ cảnh |
| Muốn đọc detail theo kiểu yêu cầu | Generic method `<T> T detailAs(Class<T>)`, hoặc trường cụ thể | Có thể kiểm tra kiểu runtime bằng `Class<T>` |
| Muốn phân loại nhiều loại lỗi để phản hồi khác nhau | Các `catch` cụ thể, thứ tự chuyên biệt → tổng quát | Phù hợp cơ chế JVM và hợp đồng Java |

Đừng tạo một phân cấp exception quá sâu chỉ để mô phỏng các tham số generic. Chọn lớp ngoại lệ đại diện cho **ý nghĩa lỗi cần bắt hoặc truyền**, còn dữ liệu bổ sung mang theo lỗi có thể nằm trong các trường có kiểu.

## 13. Những lỗi hiểu sai và cách sửa

| Hiểu sai | Kết quả thực tế | Cách sửa |
| --- | --- | --- |
| “`Exception<T>` hoặc `RuntimeException<T>` là kiểu chuẩn của JDK.” | Các lớp đó không generic. | Dùng `Exception`, `RuntimeException` hoặc custom exception không generic. |
| “Chỉ `extends Throwable` trực tiếp mới bị cấm.” | Kế thừa gián tiếp cũng bị cấm. | Kiểm tra toàn chuỗi lớp cha. |
| “Thêm một lớp ngoại lệ trung gian giúp hợp lệ hóa `Failure<T>`.” | Không; `Failure<T>` vẫn là subclass of Throwable. | Chuyển T sang field, method hoặc result holder. |
| “Tạo generic exception rồi phân biệt `catch (Failure<String>)` với `catch (Failure<Integer>)`.” | Không có lớp generic exception hợp lệ; type erasure cũng không cho handler phân biệt kiểu tham số. | Sử dụng lớp ngoại lệ cụ thể khác nhau khi thật sự cần phân nhánh runtime. |
| “Có giới hạn này nên exception không được chứa `List<String>`.” | Trường generic trong non-generic exception là hợp lệ. | Khai báo trường có kiểu, không thêm `<T>` lên lớp. |
| “Phương thức generic không thể ném checked exception.” | `throws E` được phép nếu bound phù hợp. | Sử dụng generic `throws` có chủ đích. |
| “Nếu `throws E` hợp lệ thì `catch (E ex)` cũng hợp lệ.” | JLS cấm type variable trong exception parameter. | Bắt lớp cụ thể hoặc truyền lỗi lên trên. |
| “Một lớp `Result<T,E>` chứa lỗi cũng bị cấm.” | Chỉ bị cấm nếu lớp generic đó là subclass of Throwable. | Giữ Result là lớp dữ liệu, không extends Throwable. |
| “`T extends Throwable` tự động tạo ngoại lệ lớp `T` mới.” | Type variable không phải constructor/lớp runtime mới. | Nhận đối tượng lỗi hoặc dùng factory rõ ràng. |
| “Cứ dùng `catch(Exception)` là đúng khi viết mã generic.” | Bắt quá rộng có thể che lỗi ngoài chính sách. | Cân nhắc throws E hoặc các catch cụ thể. |
| “Lưu metadata vào `Object` rồi ép kiểu tùy ý là type-safe.” | Có thể gây `ClassCastException`. | Ưu tiên trường có kiểu hoặc `Class<T>.cast` kiểm tra. |
| “Muốn một lỗi mang T thì phải `extends Exception<T>`.” | JDK `Exception` không có type parameter; custom generic exception bị cấm. | Thiết kế non-generic exception chứa metadata có kiểu, hoặc generic result. |

## 14. Quy trình chọn thiết kế cho custom exception

Khi muốn viết `MyException<T>`, thử làm theo các bước:

**Bước 1 — Xác định điều đang được generic hóa.** Đó là loại dữ liệu của lỗi, loại kết quả, chiến lược xử lý hay danh tính class ngoại lệ? Nếu chỉ là thông tin liên quan tới sự cố, nó thường nên là **field**, không phải tham số của lớp exception.

**Bước 2 — Định nghĩa các kiểu ngoại lệ mà `catch` cần phân biệt.** Nếu người gọi cần xử lý “sai định dạng” khác với “thiếu tệp”, có thể dùng hai lớp ngoại lệ cụ thể không generic hoặc một lớp chung với mã lỗi ổn định, tùy hợp đồng.

**Bước 3 — Giữ nguyên nhân gốc.** Custom exception nên có constructor nhận `(String message, Throwable cause)` khi chuyển lỗi từ tầng dưới. Không thay `cause` chỉ bằng `cause.getMessage()`.

**Bước 4 — Chuyển tính generic tới nơi hợp lệ.** Sử dụng generic method để viết thuật toán dùng lại hoặc generic result holder nếu cần mang theo một giá trị T và một lỗi E.

**Bước 5 — Kiểm tra vị trí tham số kiểu.** Khai báo lớp exception **không có `<T>`**; nếu type variable nằm trong `throws E` thì bound phải thích hợp; trong `catch (E ex)` thì không hợp lệ.

**Bước 6 — Kiểm tra checked exception.** Các phương thức có thể ném checked exception phải được `catch` hoặc khai báo `throws` đúng kiểu, kể cả khi mã gọi nằm trong một lớp generic.

**Bước 7 — Viết test với cả đường thành công lẫn thất bại.** Tránh chỉ nhìn xem đoạn mã “có vẻ generic”; hãy thực sự kiểm tra `javac`, rồi kiểm tra đúng kiểu ngoại lệ, message, cause và đầu ra.

**Bước 8 — Giới hạn metadata.** Các trường trong exception không nên lưu dữ liệu nhạy cảm rồi xuất thẳng sang log. Chỉ mang thông tin cần thiết cho quyết định xử lý và chẩn đoán.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** `class NetworkError<T> extends RuntimeException` có hợp lệ không?  
**Không.** Đây là generic class gián tiếp kế thừa `Throwable`, bị JLS §8.1.2 cấm.

**Câu 2.** `class NetworkError extends RuntimeException { List<String> hosts; }` thì sao?  
**Hợp lệ** về giới hạn generic exception. Lớp không generic, còn `List<String>` chỉ là kiểu của field.

**Câu 3.** Tại sao `catch (Failure<String>)` và `catch (Failure<Integer>)` không phải giải pháp?  
Vì generic exception class như `Failure<T>` đã bị cấm; hơn nữa, JVM không phân biệt hai tham số hóa bằng kiểu handler runtime do type erasure.

**Câu 4.** Một phương thức có thể khai báo `<E extends Exception> void relay(E ex) throws E` không?  
**Có.** JLS cho phép type variable trong mệnh đề `throws` nếu bound phù hợp.

**Câu 5.** Tại sao `catch (E ex)` không được dùng ngay trong phương thức generic nói trên?  
Vì JLS §14.20 cấm dùng type variable làm kiểu của exception parameter.

**Câu 6.** Generic `Result<T,E extends Exception>` có bị cấm không?  
**Không**, nếu nó không kế thừa trực tiếp hoặc gián tiếp `Throwable`.

**Câu 7.** `class GenericFailure<T> extends ApplicationFailure` có hợp lệ khi `ApplicationFailure extends RuntimeException` không?  
**Không.** Lớp generic đó vẫn là subclass gián tiếp của `Throwable`.

**Câu 8.** Một lớp exception không generic có thể khai báo `<T> T detailAs(Class<T> type)` không?  
**Có.** Generic method không biến chính lớp exception thành generic.

**Câu 9.** `throw ex;` với `E extends Exception` có thể biên dịch trong generic method không?  
**Có**, nếu hợp đồng checked exception được đáp ứng, ví dụ phương thức khai báo `throws E`.

**Câu 10.** Nhu cầu chính là một lỗi kèm thông tin `List<String>`. Nên làm gì?  
Thường tạo **non-generic custom exception** với trường `List<String>` và constructor phù hợp. Chỉ dùng Result holder nếu mô hình giao tiếp chủ đích muốn biểu diễn thành công/thất bại dưới dạng giá trị.

## Tài liệu chuẩn

- [Java Language Specification 21 — §8.1.2 Generic Classes and Type Parameters](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.1.2): giới hạn generic subclass of `Throwable`.
- [JLS 21 — §8.4.6 Method Throws](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.4.6): type variable được phép xuất hiện trong mệnh đề `throws`.
- [JLS 21 — §14.20 The `try` Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.20): type variable không được dùng làm kiểu tham số `catch`.
- [JLS 21 — §14.18 The `throw` Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.18): quy tắc ném đối tượng ngoại lệ.
- [JLS 21 — §4.6 Type Erasure](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.6): ý nghĩa của việc xóa thông tin kiểu generic.
- [JLS 21 — §11.2 Compile-Time Checking of Exceptions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-11.html#jls-11.2): checked exception và nghĩa vụ `catch`/`throws`.

**Ghi nhớ:** Java **cấm generic class là lớp con của `Throwable`**, nhưng **không cấm dùng generic field, generic method, generic result holder hay `throws E`** để làm việc với ngoại lệ. Chọn một lớp ngoại lệ không generic mang ý nghĩa lỗi ổn định, giữ metadata bằng trường có kiểu, và chỉ generic hóa phần thuật toán hoặc dữ liệu thực sự cần tính tổng quát.
