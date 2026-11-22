# Phân biệt kiểu trong catch với tham số kiểu được dùng trong throws của Java Generics

## 1. Câu hỏi cốt lõi: vì sao throws E hợp lệ nhưng catch (E e) không hợp lệ?

Một phương thức generic trong Java có thể khai báo **tham số kiểu ngoại lệ** trong mệnh đề `throws`:

~~~java
static <E extends Exception> void relay(E problem) throws E {
    throw problem;
}
~~~

Khai báo này **hợp lệ**: compiler biết `E` là subtype của `Exception` và dùng `throws E` để mô tả hợp đồng về loại ngoại lệ mà caller phải xử lý hoặc khai báo tiếp.

Nhưng phương thức sau **không hợp lệ**:

~~~java
static <E extends Exception> void incorrect(E problem) throws E {
    try {
        throw problem;
    } catch (E caught) {   // Lỗi biên dịch: E là type variable.
        System.out.println(caught);
    }
}
~~~

Đây không phải hai cách dùng tương đương của `E`:

- `throws E` thuộc **hệ thống phân tích checked exceptions ở compile time**. Nó diễn đạt một loại ngoại lệ ràng buộc bởi tham số kiểu; compiler có thể kiểm tra các lời gọi theo kiểu suy luận được.
- `catch (E caught)` đòi **một exception type có thể dùng trực tiếp để chọn handler tại runtime**. Java không chấp nhận type variable làm loại ngoại lệ trong tham số của `catch`, vì thông tin type argument thường bị xóa bởi **type erasure**.
- `catch (IOException caught)` hay `catch (Exception caught)` hợp lệ, bởi các tên này là **class exception cụ thể**, có class identity để runtime xác định handler phù hợp.
- Các class exception không được tự khai báo generic type parameter: `class ErrorData<T> extends Exception` cũng không hợp lệ.

Mấu chốt của bài: **`throws` và `catch` có nhiệm vụ khác nhau trong ngôn ngữ**. `throws E` không hứa rằng JVM có thể tạo một nhánh catch hoạt động theo E sau erasure.

## 2. Quy tắc đối với throws và catch

### 2.1. `throws` mô tả ngoại lệ có thể thoát khỏi phương thức

Ví dụ quen thuộc:

~~~java
static void readFile() throws java.io.IOException {
    // Có thể ném IOException.
}
~~~

Một method declaration có thể chứa:
- Tên exception class `IOException`.
- Nhiều kiểu exception class phân tách bằng dấu phẩy.
- **Type variable** nếu giới hạn trên phù hợp với Throwable, ví dụ `<E extends Exception> ... throws E`.

Java phân biệt **checked exceptions** như `IOException`, `SQLException` với **unchecked exceptions** (ví dụ `RuntimeException`, `Error` và các subtype của chúng). Đối với checked exception, caller thường phải catch hoặc tiếp tục khai báo `throws`.

### 2.2. `catch` lựa chọn handler theo class ngoại lệ

~~~java
try {
    doWork();
} catch (java.io.IOException problem) {
    // Xử lý IOException và các subclass.
}
~~~

Runtime so khớp đối tượng ngoại lệ đã ném với các lớp exception trong các catch clauses theo thứ tự; nhánh đầu tiên phù hợp được chọn. Điều đó dựa trên quan hệ **class/subclass runtime**, không phải type argument generic của caller.

Ví dụ:

~~~java
try {
    doWork();
} catch (java.io.IOException | java.sql.SQLException problem) {
    // Multi-catch: xử lý một trong hai exception classes.
}
~~~

Đây là **multi-catch**. Dấu `|` liệt kê các class ngoại lệ được phép theo quy tắc Java, không phải một cú pháp tổng quát để catch mọi `E` tùy ý.

### 2.3. Khác biệt tổng hợp

| Đặc điểm | `throws E` | `catch (E e)` |
| --- | --- | --- |
| Vai trò | Hợp đồng checked-exception ở compile time. | Chọn handler xử lý ngoại lệ tại runtime. |
| E là type variable? | Được phép khi bounded đúng với Throwable. | Không được phép. |
| Có cần class exception cụ thể làm token bắt không? | Không nhất thiết tại source; erasure áp dụng khi sinh descriptor. | Có: catch parameter phải dùng exception class hợp lệ, không dùng type variable. |
| Liên quan type inference? | Có, caller có thể suy luận E và compiler xác định nghĩa vụ xử lý checked exception. | Không có catch theo type argument được suy luận. |
| Ví dụ hợp lệ | `<E extends Exception> void f() throws E`. | `catch (IOException ex)` hoặc `catch (Exception ex)`. |

**Lưu ý:** `throws E` không phải cam kết rằng “mỗi invocation chỉ có một object exception class được lưu sẵn trong E ở runtime”. Nó là chữ ký generic phục vụ kiểm tra kiểu, trong khi exception object thật vẫn có runtime class của chính nó.

## 3. Vì sao Java cấm catch (E e)?

Xét:

~~~java
static <E extends Exception> void handle(E value) throws E {
    try {
        throw value;
    } catch (E problem) {
        System.out.println(problem.getMessage());
    }
}
~~~

Với `E extends Exception`, erasure của `E` là `Exception`. Nếu compiler cho phép `catch(E)` và đơn giản biến nó thành `catch(Exception)`, nó sẽ bắt **mọi Exception phù hợp với bound**, không chỉ lớp cụ thể mà caller đã gắn cho E.

Ví dụ, cùng method về mặt source có thể được gọi với `E = IOException` hoặc `E = SQLException`, nhưng JVM không có một handler table phân biệt hai type arguments cho từng invocation generic. Biến kiểu không biến thành một class runtime chuyên biệt cho mỗi lần gọi.

Do đó, Java yêu cầu kiểu catch là **exception class cụ thể**. Ví dụ biên dịch được:

~~~java
static <E extends Exception> void handle(E value) throws E {
    try {
        throw value;
    } catch (Exception problem) {
        System.out.println(problem.getMessage());
    }
}
~~~

Đoạn này hợp lệ nhưng **`catch(Exception)` bắt theo Exception**, không bắt theo E. Nếu mục tiêu là xử lý riêng IOException, có thể viết `catch(IOException)` khi compiler xác định loại ngoại lệ đó có thể được ném và đoạn code hợp lệ theo exception analysis.

**Lỗi cụ thể của javac 17** với `catch(E problem)` có dạng:

~~~text
error: unexpected type
required: class
found:    type parameter E
~~~

Điều quan trọng ở chẩn đoán: compiler yêu cầu một **class**, không chấp nhận một **type parameter** ở vị trí đó.

## 4. Điều kiện hợp lệ của E trong throws

Một type variable muốn xuất hiện trong mệnh đề `throws` phải có giới hạn thích hợp: nó đại diện cho subtype của `Throwable`.

Ví dụ:

~~~java
static <E extends Exception> void pass(E problem) throws E {
    throw problem;
}
~~~

Hợp lệ; `E` là một subtype của `Exception` nên cũng là subtype của `Throwable`.

Một biến thể tổng quát hơn:

~~~java
static <E extends Throwable> void passAnything(E problem) throws E {
    throw problem;
}
~~~

Hợp lệ; nó có thể đại diện cho checked exceptions, unchecked exceptions hoặc Error tùy invocation. Tuy nhiên, dùng `Throwable` ở API công khai thường tạo hợp đồng quá rộng; đa số ứng dụng nên ưu tiên `Exception` hoặc một checked exception cụ thể, trừ khi có lý do rõ ràng.

Ngược lại, câu sau không hợp lệ:

~~~java
// static <E> void bad() throws E { }
// E mặc định chỉ có bound Object, không được bảo đảm là Throwable.
~~~

Tương tự, không phải mọi type variable có bound là `Object`, `Serializable` hay một interface nghiệp vụ đều có thể đứng trong `throws` nếu compiler không chứng minh được chúng là subtype của Throwable.

### Khi type variable bị xóa thì throws còn tác dụng gì?

Java thường xóa tham số kiểu `E extends Exception` theo bound `Exception` ở những nơi cần type erasure. Nhưng compiler sử dụng generic signature và type inference ở **mã nguồn caller** để quyết định checked exception tương ứng.

Kết quả là:
- Caller của method generic có thể được kiểm tra với IOException hoặc một exception type cụ thể.
- Runtime vẫn nhận object IOException thật nếu nó được ném.
- Không có phép `catch(E)` động nào được sinh ra.

## 5. Ví dụ đơn giản: một method generic “ném lại đúng kiểu”

Đây là method hợp lệ:

~~~java
static <E extends Exception> void relay(E problem) throws E {
    throw problem;
}
~~~

Cách gọi:

~~~java
try {
    relay(new java.io.IOException("network"));
} catch (java.io.IOException problem) {
    System.out.println(problem.getMessage());
}
~~~

Ở vị trí invocation, compiler có thể suy luận `E = IOException`, nên caller xử lý bằng `catch(IOException)`. Runtime nhận IOException đúng như object được ném.

Đây **không** phải một ví dụ dùng `catch(E)`. Caller bắt **IOException**, một class exception thật, trong khi `E` chỉ xuất hiện trong chữ ký của method generic.

Nếu caller không bắt hoặc tiếp tục khai báo checked exception thích hợp, compiler có thể báo:

~~~text
unreported exception IOException; must be caught or declared to be thrown
~~~

Đó là tác dụng của hợp đồng `throws E` ở compile time.

## 6. Generic functional interface có exception type riêng

Một tình huống áp dụng thực tế hơn là truyền một hành động có checked exception mà nó được phép ném:

~~~java
@FunctionalInterface
interface CheckedAction<E extends Exception> {
    void run() throws E;
}
~~~

Ví dụ adapter:

~~~java
static <E extends Exception> void execute(CheckedAction<E> action) throws E {
    action.run();
}
~~~

Đặc điểm:

- `CheckedAction<E>` giữ E như một tham số generic của hợp đồng hàm.
- `run() throws E` cho phép implementation ném một checked exception thuộc E.
- `execute(...) throws E` chuyển tiếp hợp đồng mà không cần bắt ngoại lệ.
- Caller có thể gán `CheckedAction<IOException>` và bắt IOException cụ thể.

Đoạn sử dụng:

~~~java
CheckedAction<java.io.IOException> action =
        () -> { throw new java.io.IOException("read failed"); };

try {
    execute(action);
} catch (java.io.IOException problem) {
    System.out.println(problem.getMessage()); // read failed.
}
~~~

Điều này rất hữu ích khi viết callback API, transaction wrapper, job runner hoặc utility xử lý checked exceptions mà không muốn ép mọi caller về `throws Exception` rộng hơn mức cần thiết.

Nếu có nhiều loại checked exception độc lập, một tham số `E` không nhất thiết diễn đạt toàn bộ các loại ngoại lệ chính xác như một chữ ký liệt kê nhiều class. Khi thiết kế API cần cân nhắc mức trừu tượng, bounds và cách xử lý.

## 7. Muốn bắt ngoại lệ tại runtime theo E thì làm thế nào?

Java không chấp nhận:

~~~java
// catch (E e) { ... } // Không hợp lệ.
~~~

Nhưng một method generic có thể dùng **runtime class token** `Class<E>` cùng một catch class cụ thể:

~~~java
static <E extends Exception> void inspectThenRethrow(
        CheckedAction<E> action, Class<E> type) throws E {

    try {
        action.run();
    } catch (Exception actual) {
        if (type.isInstance(actual)) {
            System.out.println(
                    "caughtRuntime=" +
                    actual.getClass().getSimpleName()
            );
            throw type.cast(actual);
        }

        throw new IllegalStateException(
                "Unexpected exception", actual
        );
    }
}
~~~

Ở đây:

1. `catch (Exception actual)` là một handler hợp lệ cho class Exception.
2. `type` là một **Class<E> token** được caller cung cấp, ví dụ `IOException.class`.
3. `type.isInstance(actual)` hỏi runtime object exception có tương thích với class trong token không.
4. `type.cast(actual)` thực hiện checked cast với class token rồi cho giá trị E ở mức source.
5. `throw type.cast(actual)` thỏa `throws E` ở chữ ký method.
6. Nếu exception không tương thích, ví dụ này bọc nó trong một `IllegalStateException` thay vì gán sai thành E.

**Không đồng nhất điều này với catch(E):** JVM vẫn chọn handler `Exception` trước; sau khi vào nhánh, code chủ động kiểm tra runtime class. Cách làm có token phù hợp khi thật sự cần phân biệt một exception type động do caller cung cấp.

### Vì sao nên xử lý trường hợp ngoại lệ không tương thích?

Nếu method tự ý ép mọi Exception thành E bằng unchecked cast, runtime có thể tạo một hợp đồng giả và phát `ClassCastException` tại nơi khác. Với class token, method có thể **kiểm tra chính xác class runtime** hoặc quyết định bọc/đưa ngoại lệ khác đi theo một đường rõ ràng.

Trong ví dụ, `IllegalStateException` là unchecked exception. API sản phẩm có thể chọn quy tắc khác, ví dụ thêm type parameter hoặc kiểu trả về kết quả, nhưng phải mô tả hợp đồng cụ thể. Đừng giả định mọi Exception bắt được đều là E chỉ vì hành động có chữ ký `throws E`: một exception unchecked khác vẫn có thể phát sinh trong implementation.

## 8. Chương trình Java 17+ hoàn chỉnh và chạy được

Lưu tệp sau với tên **GenericExceptionDemo.java**:

~~~java
import java.io.IOException;
import java.sql.SQLException;

public class GenericExceptionDemo {
    @FunctionalInterface
    interface CheckedAction<E extends Exception> {
        void run() throws E;
    }

    static <E extends Exception> void execute(
            CheckedAction<E> action) throws E {
        action.run();
    }

    static <E extends Exception> void relay(E problem) throws E {
        throw problem;
    }

    static <E extends Exception> void inspectThenRethrow(
            CheckedAction<E> action, Class<E> type) throws E {

        try {
            action.run();
        } catch (Exception actual) {
            if (type.isInstance(actual)) {
                System.out.println(
                        "caughtRuntime=" +
                        actual.getClass().getSimpleName()
                );
                throw type.cast(actual);
            }

            throw new IllegalStateException(
                    "Unexpected exception", actual
            );
        }
    }

    // Java 7+ precise rethrow; xem phần 11.
    static void precise(boolean io) throws IOException, SQLException {
        try {
            if (io) {
                throw new IOException("disk");
            }
            throw new SQLException("database");
        } catch (Exception exception) {
            throw exception;
        }
    }

    public static void main(String[] args) {
        CheckedAction<IOException> ioAction = () -> {
            throw new IOException("read failed");
        };

        try {
            execute(ioAction);
        } catch (IOException problem) {
            System.out.println(
                    "execute=" + problem.getMessage()
            );
        }

        try {
            relay(new IOException("network"));
        } catch (IOException problem) {
            System.out.println(
                    "relay=" + problem.getMessage()
            );
        }

        try {
            inspectThenRethrow(
                    ioAction, IOException.class
            );
        } catch (IOException problem) {
            System.out.println(
                    "typedRethrow=" + problem.getMessage()
            );
        }

        try {
            precise(false);
        } catch (IOException | SQLException problem) {
            System.out.println(
                    "precise=" +
                    problem.getClass().getSimpleName()
            );
        }
    }
}
~~~

Biên dịch và chạy bằng JDK hỗ trợ Java 17:

~~~bash
javac --release 17 -Xlint:all GenericExceptionDemo.java
java GenericExceptionDemo
~~~

**Stdout chính xác:**

~~~text
execute=read failed
relay=network
caughtRuntime=IOException
typedRethrow=read failed
precise=SQLException
~~~

Chương trình này được thiết kế để không cần raw types hoặc unchecked casts. Nó minh họa kiểu ngoại lệ ở `throws E` vẫn có ý nghĩa với caller trong khi handler runtime được viết bằng **class exception hợp lệ**.

### Giải thích từng dòng kết quả

- `execute=read failed`: `CheckedAction<IOException>` giữ hợp đồng ngoại lệ IOException; caller catch IOException như bình thường.
- `relay=network`: method `relay` ném chính object IOException, caller bắt bằng exception class IOException.
- `caughtRuntime=IOException`: bên trong `inspectThenRethrow`, `catch(Exception)` bắt object, token `IOException.class` xác định loại runtime phù hợp và in ra tên class.
- `typedRethrow=read failed`: method tiếp tục ném cùng exception theo chữ ký `throws E`; caller xử lý IOException.
- `precise=SQLException`: nhánh `precise(false)` ném SQLException, handler multi-catch bắt đúng class và in tên class.

Mỗi dòng minh họa cách **static checked-exception contract**, **runtime exception class** và **catch handler** phối hợp mà không phải dùng `catch(E)`.

## 9. Các trường hợp cố ý sai: kiểm chứng qua javac

Đoạn sau **không phải** mã chạy được. Lưu riêng thành **InvalidGenericExceptions.java** nếu muốn xem compiler diagnostics:

~~~java
class InvalidGenericExceptions {
    static <E extends Exception> void bad(E input) throws E {
        try {
            throw input;
        } catch (E exception) {  // Không hợp lệ: E là type variable.
            System.out.println(exception);
        }
    }
}

class GenericProblem<T> extends Exception {
    // Không hợp lệ: generic class kế thừa Throwable.
}

class GenericRuntimeProblem<T> extends RuntimeException {
    // Cũng không hợp lệ.
}
~~~

Biên dịch để thấy lỗi:

~~~bash
javac --release 17 InvalidGenericExceptions.java
~~~

Những chẩn đoán quan trọng:

~~~text
error: unexpected type
required: class
found:    type parameter E

error: a generic class may not extend java.lang.Throwable
~~~

Compiler thường phát một lỗi riêng cho `catch(E)` và mỗi generic class kế thừa Throwable. Lý do không phụ thuộc class đó kế thừa trực tiếp Throwable hay gián tiếp qua Exception/RuntimeException: **không thể khai báo generic subclass của Throwable**.

Đừng trộn file chứa mã cố ý sai với `GenericExceptionDemo.java` khi mục đích là biên dịch/running chương trình hoàn chỉnh.

## 10. Vì sao catch theo type argument không khả thi dù method biết `E`?

Điểm dễ nhầm là **một object exception có runtime class cụ thể** không đồng nghĩa compiler có thể chuyển **type variable `E`** thành một exception handler riêng. Với `<E extends Exception>`, thông tin `E` thuộc hợp đồng generic tại compile time; cùng method có thể được gọi ở ngữ cảnh suy luận `E = IOException` hoặc `E = SQLException`. JVM không tạo một handler mới cho mỗi type argument đó.

Vì thế đoạn sau **cố ý không biên dịch**:

~~~java
static <E extends Exception> void bad(E failure) throws E {
    try {
        throw failure;
    } catch (E caught) { // Type variable không phải catch parameter type hợp lệ.
        System.out.println(caught);
    }
}
~~~

Dùng `catch (Exception actual)` hoặc một exception class cụ thể nếu muốn **bắt lỗi**, sau đó có thể kiểm tra `Class<E> token` bằng `token.isInstance(actual)` hoặc `token.cast(actual)` theo hợp đồng rõ ràng. Nhưng runtime token **không làm** cú pháp `catch(E)` trở nên hợp lệ.

Java cũng cấm **generic subclass của `Throwable`** (kể cả dưới `RuntimeException`), nên không thể “vòng qua” bằng một `GenericError<E>` để phân biệt các handler theo type argument. Một lớp exception không generic vẫn có thể có generic methods, constructor hoặc payload được giữ bằng wrapper.

**Nội dung riêng cần nhớ ở đây:** `throws E` được compiler dùng để theo dõi checked exception từ lời gọi; `catch` của JVM dùng runtime exception class. Hai cơ chế phục vụ hai nhiệm vụ khác nhau, dù cùng nằm trong xử lý lỗi.

## 11. Precise rethrow: catch(Exception) nhưng vẫn giữ loại checked exception hẹp

Một trường hợp dễ nhầm với `throws E` là **precise rethrow analysis** từ Java 7.

~~~java
static void precise(boolean io)
        throws java.io.IOException, java.sql.SQLException {

    try {
        if (io) {
            throw new java.io.IOException("disk");
        }
        throw new java.sql.SQLException("database");
    } catch (Exception exception) {
        throw exception;
    }
}
~~~

Ở đây catch parameter có kiểu **Exception**, không phải type variable E. Tuy nhiên compiler phân tích:
- Trong try có thể phát sinh IOException hoặc SQLException.
- Catch parameter `exception` không bị gán lại (effectively final).
- `throw exception` trong catch có thể được phân tích chính xác theo các exception types từ try.

Do đó method vẫn có thể khai báo `throws IOException, SQLException` mà không cần khai báo một `throws Exception` rộng.

Điều này hoàn toàn khác với việc cho phép `catch(E)`. Precise rethrow là một **quy tắc phân tích loại ngoại lệ ở compile time**, không phải catch runtime theo generic type argument.

### Điều kiện effectively final rất quan trọng

Nếu bạn gán lại catch parameter rồi ném nó, compiler có thể không còn suy luận hẹp theo cách precise rethrow và phải xem xét kiểu khai báo `Exception` rộng hơn. Khi đó, một method chỉ `throws IOException, SQLException` có thể không còn biên dịch.

Vì vậy, khi cần bắt để log rồi ném lại, giữ catch parameter không bị gán lại:

~~~java
try {
    riskyOperation();
} catch (Exception problem) {
    log(problem);
    throw problem;
}
~~~

Đoạn trên là **mảnh mã minh họa**, cần phương thức `riskyOperation()` và `log(...)` trong chương trình thực tế; quy tắc ngoại lệ cụ thể vẫn phụ thuộc các checked exceptions được biết từ khối try.

## 12. Multi-catch có thay thế được catch(E) không?

Multi-catch:

~~~java
try {
    work();
} catch (java.io.IOException | java.sql.SQLException problem) {
    System.out.println(problem.getMessage());
}
~~~

có thể xử lý nhiều class exception cụ thể trong một handler.

Nhưng nó **không** có nghĩa “catch một generic type union E”. Ví dụ sau vẫn sai:

~~~java
// catch (E | IOException problem) { }
// E là type variable, không được dùng làm catch type.
~~~

Trong multi-catch, các exception alternatives phải là các class exception hợp lệ; không được có một alternative là subtype của alternative khác trong cùng multi-catch, và biến multi-catch là implicitly final.

Nếu cần logic chung cho nhiều class ngoại lệ, có thể:
- Dùng multi-catch khi danh sách class hữu hạn và đã biết.
- Catch một superclass thích hợp và phân nhánh bằng `instanceof`.
- Dùng class token nếu exception class mục tiêu được truyền vào runtime.
- Để exception đi tiếp qua `throws E` nếu method không cần xử lý.

Chọn giải pháp theo mục tiêu xử lý runtime và hợp đồng compile-time, không theo việc có type parameter trong chữ ký hay không.

## 13. Overriding, checked exceptions và generic throws

Khi ghi đè một method, Java không cho subclass tùy ý mở rộng tập **checked exceptions** được phép thoát ra ngoài so với hợp đồng supertype.

Ví dụ:

~~~java
class BaseJob {
    void run() throws java.io.IOException {
    }
}

class SpecificJob extends BaseJob {
    @Override
    void run() throws java.io.FileNotFoundException {
    }
}
~~~

Hợp lệ vì FileNotFoundException là subtype của IOException.

Ngược lại, một override chỉ muốn thêm `SQLException` vào method có hợp đồng `throws IOException` sẽ không hợp lệ nếu checked exception đó không được cho phép bởi quy tắc override.

Với generic methods có `throws E`, compiler cũng kiểm tra mối quan hệ giữa chữ ký được kế thừa và method override sau các phép thay thế kiểu phù hợp. `throws E` không cho phép một implementation phớt lờ contract exception của interface/base class.

**Ý nghĩa thực hành:** `throws E` là cách mô hình hóa checked-exception contract, không phải một escape hatch để mọi subclass ném thêm bất kỳ checked exception nào.

## 14. Type inference ở throws E: đừng nhầm với catch runtime

Khi gọi:

~~~java
static <E extends Exception> void relay(E problem) throws E {
    throw problem;
}

relay(new java.io.IOException("network"));
~~~

type inference có thể xác định E theo biểu thức đối số. Với checked exception IOException, caller phải xử lý phù hợp.

Nhưng nếu truyền một biến có kiểu tĩnh rộng hơn:

~~~java
Exception general = new java.io.IOException("network");
relay(general);
~~~

compiler có thể suy luận E là `Exception` theo kiểu tĩnh biến `general`, dù object thực tế là IOException. Khi đó **hợp đồng compile time rộng hơn**; caller cần catch Exception hoặc khai báo tương ứng.

Runtime vẫn ném đúng đối tượng IOException gốc. Đây là ví dụ rõ nhất để tách:
- **Kiểu tĩnh và type inference của E** trong `throws`.
- **Class runtime thực sự của exception object**.
- **Catch handler** mà caller dùng để xử lý.

Không được giả định compiler suy luận E dựa trên runtime class của dữ liệu trong biến `Exception general`.

### Vì sao generic throws không tự là một “sneaky throw” API đáng dùng?

Có thể bắt gặp các kỹ thuật dùng generic type inference và unchecked casts để lách quy tắc checked exceptions. Chúng không cần thiết cho việc hiểu khác biệt giữa `throws E` và `catch(E)`, và dễ làm hợp đồng API trở nên khó đoán.

Trong code nghiệp vụ, ưu tiên khai báo đúng checked exceptions hoặc dùng abstraction rõ như `CheckedAction<E>`. Đừng sử dụng thủ thuật exception typing để che checked exception khỏi caller khi họ cần được biết và xử lý nó.

## 15. Class<E> token giải quyết được và không giải quyết được gì?

Với:

~~~java
static <E extends Exception> boolean matches(
        Exception problem, Class<E> type) {
    return type.isInstance(problem);
}
~~~

Caller có thể hỏi:

~~~java
boolean io = matches(
        new java.io.IOException("disk"),
        java.io.IOException.class
); // true.
~~~

Đây là **runtime class matching hợp lệ**. Nó kiểm tra trực tiếp object ngoại lệ theo class token.

Nhưng class token **không thay đổi cú pháp catch**:
- Không thể viết `catch(type)`.
- Không thể viết `catch(E problem)` chỉ vì đang giữ `Class<E>`.
- Handler runtime vẫn được khai báo bằng exception class như `Exception` hoặc `IOException`.
- Khi đã catch một class rộng, bên trong mới dùng `type.isInstance(...)` để phân biệt.

Nếu cần xử lý một số loại checked exceptions cụ thể mà không muốn catch `Exception` quá rộng, có thể thiết kế API với nhiều catch clauses cụ thể hoặc phân tách logic tại caller. Token động không thay thế mọi hình thức checked-exception analysis.

## 16. Khi nào một ngoại lệ unchecked vẫn lọt qua E?

Method:

~~~java
static <E extends Exception> void execute(
        CheckedAction<E> action) throws E {
    action.run();
}
~~~

bảo toàn checked exception contract của E. Nhưng body callback vẫn có thể ném một `NullPointerException`, `IllegalArgumentException` hoặc subclass khác của RuntimeException.

Những ngoại lệ unchecked đó **không bắt buộc phải khai báo trong throws**. Vì vậy, nói rằng `execute(... ) throws E` “chỉ có thể ném chính xác E và không có exception nào khác” là sai.

Đó là lý do phương thức `inspectThenRethrow` ở ví dụ phải quyết định xử lý thế nào khi `catch(Exception)` bắt một exception không đúng class token. Nó không nên ép mù quáng thành E.

Tương tự, `Error` không phải subtype của Exception nên `catch(Exception)` không bắt `Error`. Nếu API đặc biệt cần xử lý Throwable rộng, đó là một quyết định khác với tác động đáng kể đến cách xử lý lỗi nghiêm trọng; tránh catch Throwable một cách máy móc.

## 17. Lỗi thường gặp khi review Java Generics và exceptions

### Lỗi A — thấy throws E rồi viết catch(E)

~~~java
// <E extends Exception> ... throws E
// catch (E e) { } // Bị compiler từ chối.
~~~

**Sửa:** Catch một exception class thật; hoặc để ngoại lệ propagate theo `throws E`.

### Lỗi B — biến exception subclass thành generic class

~~~java
// class Failure<T> extends RuntimeException {} // Không hợp lệ.
~~~

**Sửa:** Non-generic exception class, gắn payload qua Object hoặc wrapper được kiểm soát, giữ generic typing ở tầng API phù hợp.

### Lỗi C — nghĩ bound E extends Exception làm E reifiable

Type variable không tự trở thành class runtime có thể catch. Runtime object có class cụ thể, nhưng E ở chữ ký generic vẫn chịu erasure.

### Lỗi D — dùng catch(Exception) rồi giả định mọi thứ bắt được là E

Có thể có unchecked exceptions không tương thích với token E. Dùng `Class<E>.isInstance` hoặc chính sách khác thay vì unchecked cast.

### Lỗi E — nhầm multi-catch và generic catch

`catch(IOException | SQLException ex)` sử dụng hai classes cụ thể. Nó không nhận một type parameter đại diện cho union.

### Lỗi F — khai báo throws Exception dù method chỉ ném IOException

Một hợp đồng `throws Exception` rộng hơn cần thiết làm tăng gánh nặng cho caller. Dùng `throws IOException` hoặc `throws E` khi E thực sự có vai trò mô hình hóa typed callback.

### Lỗi G — gán lại catch parameter rồi mong precise rethrow vẫn thu hẹp

Precise rethrow dựa vào exception analysis và điều kiện catch parameter effectively final. Đừng phá điều kiện đó nếu muốn giữ chữ ký throws hẹp.

### Lỗi H — gắn @SuppressWarnings lên unchecked cast ngoại lệ mà không hiểu nguồn gốc

Suppress không thay runtime exception class hoặc đảm bảo dữ liệu thực sự là E. Nếu cần kiểm tra động, hãy dùng runtime class token phù hợp.

## 18. Quy trình chọn giải pháp

Khi thiết kế method xử lý ngoại lệ trong generic API:

1. **Bạn cần xử lý ngoại lệ hay chỉ chuyển tiếp?** Nếu chỉ chuyển tiếp, cân nhắc `throws E` để giữ hợp đồng checked exception của callback.
2. **Kiểu checked exception có cố định không?** Nếu là IOException/SQLException đã biết, khai báo trực tiếp thường rõ hơn generic E.
3. **Bạn có định viết catch(E) không?** Hãy thay đổi thiết kế: Java không chấp nhận type variable trong catch.
4. **Runtime cần phân biệt exception class động không?** Nhận thêm `Class<E>`, bắt một class thích hợp rồi dùng `isInstance/cast`.
5. **Một generic exception class có cần thiết không?** Không thể dùng generic class làm subclass Throwable; chuyển generic information ra class wrapper/API khác.
6. **Bạn catch rộng để log rồi rethrow?** Kiểm tra precise rethrow và catch parameter effectively final.
7. **Bạn có bắt RuntimeException/Error ngoài ý muốn không?** Viết rõ chính sách ứng với checked, unchecked và fatal errors.
8. **Có override method không?** Giữ hợp đồng checked exception compatible với supertype.
9. **Có dùng generic inference cho E không?** Nhớ rằng inference dựa trên kiểu tĩnh tại call site, không theo runtime class của exception đang cất trong biến rộng.
10. **Kiểm chứng javac với source release mục tiêu**, ví dụ `javac --release 17`, và thử cả ví dụ đúng lẫn sai để thấy nơi compiler yêu cầu class exception thật.

## 19. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `static <E extends Exception> void f() throws E` được phép nhưng `catch(E e)` không được phép?

**Đáp án:** `throws E` là hợp đồng checked exception tại compile time; `catch` cần một exception class runtime. E là type variable bị erasure, không dùng trực tiếp để xác định handler.

**Câu 2.** `E extends Throwable` có dùng ở `throws E` được không?

**Đáp án:** Có. E được đảm bảo là subtype của Throwable. Tuy nhiên contract rộng như vậy có thể bao gồm các Error/unchecked exception nên nên dùng theo nhu cầu cụ thể.

**Câu 3.** Có thể viết `class Failure<T> extends Exception` không?

**Đáp án:** Không. Java cấm generic class là subclass của Throwable, dù trực tiếp hay gián tiếp.

**Câu 4.** Một method nhận `CheckedAction<IOException>` và khai báo `throws E` có buộc caller dùng `catch(E)` không?

**Đáp án:** Không. Caller có thể xử lý bằng `catch(IOException)` hoặc khai báo tiếp IOException. E được thay bằng type argument ở compile time, còn catch vẫn dùng exception class thật.

**Câu 5.** Runtime muốn biết exception có tương thích class token `IOException.class` thì làm thế nào?

**Đáp án:** Catch bằng một exception class hợp lệ trước, sau đó dùng `IOException.class.isInstance(actual)` và nếu cần `IOException.class.cast(actual)`. Điều này không biến `catch(E)` thành hợp lệ.

**Câu 6.** Precise rethrow có liên quan thế nào đến `catch(Exception)`?

**Đáp án:** Nếu try chỉ có các checked exceptions được compiler phân tích và catch parameter không bị gán lại, `throw exception` có thể giữ các loại checked exception hẹp hơn Exception trong mệnh đề throws. Không phải generic catch.

**Câu 7.** Với `Exception e = new IOException("disk"); relay(e);`, compiler nhìn E là kiểu nào?

**Đáp án:** Có thể suy luận E theo kiểu tĩnh Exception của biểu thức `e`, dù object runtime là IOException. Caller cần xử lý checked exception theo hợp đồng kiểu tĩnh rộng tương ứng.

**Câu 8.** `throws E` có bảo đảm không xảy ra NullPointerException không?

**Đáp án:** Không. RuntimeException và nhiều unchecked exceptions vẫn có thể phát sinh mà không cần khai báo trong throws.

**Câu 9.** Vì sao multi-catch `catch(IOException | SQLException ex)` hợp lệ nhưng `catch(E | IOException ex)` sai?

**Đáp án:** Multi-catch yêu cầu các alternatives là exception classes hợp lệ; E là type variable không được dùng làm catch type.

**Câu 10.** Nếu chỉ cần truyền callback có checked exception IOException qua utility generic, nên chọn gì?

**Đáp án:** Một interface như `CheckedAction<E extends Exception>` và utility `<E extends Exception> void execute(CheckedAction<E>) throws E` có thể bảo toàn checked-exception typing mà không cần catch(E) hay ép về throws Exception rộng.

## 20. Ghi nhớ

**`throws E` và `catch(E)` không đối xứng trong Java Generics.**

- `throws E` hợp lệ nếu E bị ràng buộc là một subtype của Throwable, vì compiler có thể phân tích checked-exception contract bằng generic type inference.
- `catch(E e)` không hợp lệ: handler cần exception class runtime cụ thể, không phải type variable sau erasure.
- Class ngoại lệ generic như `class Failure<T> extends Exception` cũng không hợp lệ.
- Nếu cần bắt rồi kiểm tra ngoại lệ theo kiểu động, hãy dùng một catch class hợp lệ kết hợp `Class<E>` token và `isInstance/cast`.
- Precise rethrow, multi-catch và generic throws là những tính năng **khác nhau**; chúng giải quyết những vấn đề khác nhau.

Nguyên tắc thiết kế là phân biệt rõ **kiểu tĩnh của checked exception tại lời gọi**, **class runtime của đối tượng ngoại lệ** và **loại class được ghi trong catch handler**. Hiểu được ba tầng này giúp viết generic APIs linh hoạt mà vẫn đúng quy tắc xử lý ngoại lệ của Java.
