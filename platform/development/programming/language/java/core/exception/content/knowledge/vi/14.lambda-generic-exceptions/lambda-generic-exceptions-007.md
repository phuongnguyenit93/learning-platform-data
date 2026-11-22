# Giới hạn của `catch` đối với type parameter trong Java Generic và Lambda

Trong Java, **generic type parameter** như `T`, `E` hay `X` cho phép định nghĩa phương thức và lớp dùng chung cho nhiều kiểu. Riêng với exception handling, có một giới hạn rất dễ nhầm: **Java cho phép khai báo `throws E` khi `E extends Throwable`, nhưng không cho phép viết `catch (E e)` nếu `E` là một type parameter**.

Đây không phải khác biệt về dấu ngoặc hoặc cách đặt tên. `throws E` mô tả hợp đồng checked exception cho trình biên dịch, còn `catch` là một **bộ lọc kiểu ngoại lệ khi xử lý ở runtime**; tham số kiểu generic không thể được dùng làm loại tham số của một catch clause.

Ví dụ cố ý sai:

~~~java
static <E extends Exception> void wrong(ThrowingTask<E> task) {
    try {
        task.run();
    } catch (E e) { // KHÔNG BIÊN DỊCH.
        System.out.println(e.getMessage());
    }
}
~~~

`ThrowingTask<E>` trong mảnh minh họa được giả định là functional interface có `void run() throws E`. Mặc dù `E extends Exception`, việc dùng `E` làm loại trong `catch` vẫn không hợp lệ.

Cách sửa cơ bản là **bắt một kiểu exception cụ thể** như `IOException` hoặc một superclass phù hợp như `Exception`, hoặc để ngoại lệ tiếp tục truyền ra bằng `throws E`. Nếu cần xác định một loại lỗi được biểu diễn bằng type parameter tại runtime, truyền thêm **class token `Class<E>`** và kiểm tra bằng `isInstance`/`cast` là một hướng được kiểm soát tốt hơn.

Bài học thuộc Java Core – Exception, ngữ cảnh **Lambda và generic**. Trọng tâm là quy tắc `catch` với type variable, type erasure, checked exception trong generic functional interface, giới hạn của generic exception class và các giải pháp code Java 17+.

## 1. Nhắc lại: generic type parameter là gì?

Ví dụ phương thức generic:

~~~java
static <T> T identity(T value) {
    return value;
}
~~~

Ở đây `T` là **type parameter** do phương thức khai báo. Caller có thể gọi `identity("Hello")` hoặc `identity(42)`, và trình biên dịch kiểm tra kiểu giá trị tương ứng.

Đối với ngoại lệ, có thể giới hạn type parameter:

~~~java
static <E extends Exception> void fail(E exception) throws E {
    throw exception;
}
~~~

Đoạn này là một phương thức Java **hợp lệ** trong một lớp. `E` biểu diễn một subtype của `Exception`; `throws E` được phép và `throw exception;` cũng được phép.

Ví dụ cách dùng:

~~~java
try {
    fail(new java.io.IOException("disk unavailable"));
} catch (java.io.IOException e) {
    System.out.println(e.getMessage());
}
~~~

Ở caller, kiểu exception dùng trong `catch` là **`IOException` — một class cụ thể**. Ta không viết `catch(E e)` ở phương thức generic.

**Cặp quy tắc cần phân biệt:**

| Cấu trúc | Có dùng type variable `E` được không? |
| --- | --- |
| `<E extends Exception>` | Có, khai báo type parameter có upper bound |
| `void run() throws E` | Có, khi `E` có bound phù hợp với `Throwable` |
| `throw exception;`, với biến kiểu `E` | Có |
| `catch (E e)` | **Không** |
| `catch (IOException e)` | Có, nếu các quy tắc checked/reachability khác thỏa |
| `catch (Exception e)` | Có, nếu hợp lệ với `try` tương ứng |
| `catch (IOException | SQLException e)` | Có thể, khi các alternative hợp lệ |
| `catch (E | IOException e)` | **Không**, vì `E` vẫn là type variable |

Một type variable dù tên là `ExceptionType`, `E` hay `IOExceptionLike` vẫn là **type variable**, không biến thành một class declaration có thể làm catch type.

## 2. Java dùng kiểu nào để chọn `catch`?

Khi một `Throwable` bị ném, JVM tìm handler có phạm vi phù hợp với kiểu của **đối tượng ngoại lệ thực tế**. Một catch clause điển hình:

~~~java
try {
    readFile();
} catch (java.io.IOException e) {
    System.out.println("I/O problem");
} catch (Exception e) {
    System.out.println("Another exception");
}
~~~

Đây là mảnh minh họa; `readFile()` là phương thức có thể ném `IOException`. Nếu một `IOException` được ném, handler đầu tiên có kiểu `IOException` nhận nó. Handler `Exception` rộng hơn được đặt sau.

`catch` cần một kiểu exception hợp lệ để xác định điều kiện so khớp. **Type parameter generic không biểu diễn một class riêng ở runtime.** Vì vậy compiler cấm sử dụng type variable làm catch parameter type, ngay cả khi có upper bound `Exception` hoặc `IOException`.

Một lỗi thường thấy:

~~~java
static <E extends java.io.IOException> void invalidCatch(
        ThrowingTask<E> task) {
    try {
        task.run();
    } catch (E e) { // Lỗi compile-time.
        System.out.println(e.getMessage());
    }
}
~~~

Dù `E extends IOException`, từ khóa `E` vẫn đại diện cho **một biến kiểu**, không phải class `IOException`. Upper bound làm hạn chế phạm vi của `E`, nhưng **không cho phép `catch(E)`**.

## 3. Type erasure và lý do thiết kế của giới hạn này

Java generics chủ yếu hoạt động bằng **type erasure**. Trong nhiều ngữ cảnh runtime, tham số kiểu được xóa và không có một phiên bản class runtime riêng cho mỗi tổ hợp type argument như `Box<String>` hay `Box<Integer>`.

Trong giải thích khái niệm, một type variable `E extends Exception` thường bị xóa về upper bound tương ứng là `Exception`. Nhưng **điều này không có nghĩa trình biên dịch sẽ tự chấp nhận `catch (E e)` rồi thay bằng `catch (Exception e)`**. Ngôn ngữ cấm type variable trong catch clause ngay từ compile-time.

Vì sao? Giả sử phương thức được gọi với `E = IOException` trong một lần và `E = SQLException` ở lần khác. Nếu `catch(E)` được coi là lọc **chính xác E** thì runtime cần biết type argument nào đang được dùng. Type erasure không tự tạo ra handler khác nhau theo từng instantiation của generic method.

Do đó, muốn bắt một loại exception ở runtime, ta cần **kiểu exception được xác định rõ**, hoặc một **class token** được truyền như dữ liệu:

~~~java
Class<java.io.IOException> expected = java.io.IOException.class;

Exception e = new java.io.IOException("disk failed");
System.out.println(expected.isInstance(e)); // true
~~~

`Class.isInstance` kiểm tra loại runtime thật của object, không giả vờ rằng type parameter đã được giữ nguyên để JVM tạo catch clause động.

### Type erasure không giải thích toàn bộ quy tắc bằng một câu

Nên hiểu chính xác hơn:

1. `catch` của Java có những yêu cầu ngôn ngữ riêng về **type** của catch parameter.
2. **Type variable không được dùng làm type của catch parameter**, ngay cả khi bound là exception class.
3. Type erasure giải thích vì sao type argument generic không tự trở thành một class filter runtime độc lập.
4. Khi cần so khớp động, ta làm điều đó **bên trong một handler hợp lệ** hoặc ở code thường, dùng token/reflection có hợp đồng rõ.

Không nên chỉ nói “mọi generic đều không thể dùng với `catch`”. Generic method có thể **ném checked exception generic bằng `throws E`**, và lambda có thể biểu diễn loại checked exception trong một generic functional interface.

## 4. `throws E` hoàn toàn hợp lệ khi `E` có bound phù hợp

Ví dụ:

~~~java
@FunctionalInterface
interface ThrowingAction<E extends Exception> {
    void run() throws E;
}

static <E extends Exception> void execute(
        ThrowingAction<E> action) throws E {
    action.run();
}
~~~

Đây là hai khai báo minh họa hợp lệ khi đặt trong một lớp, với interface ở phạm vi phù hợp.

Điều quan trọng:

- `E` phải có bound khiến nó là subtype của `Throwable` (ở đây chọn `Exception` để mô tả các exception thường gặp).
- `ThrowingAction<E>.run()` có thể khai báo `throws E`.
- `execute(...)` có thể lan truyền `E` bằng `throws E`.
- Caller được trình biên dịch kiểm tra checked exception theo kiểu được suy ra.

Caller:

~~~java
try {
    execute(() -> {
        throw new java.io.IOException("Cannot read");
    });
} catch (java.io.IOException e) {
    System.out.println("Caught: " + e.getMessage());
}
~~~

Trong ví dụ này, compiler có thể suy ra một loại checked exception phù hợp từ ngữ cảnh lambda và generic method. Để ví dụ hướng dẫn dễ hiểu và tránh phụ thuộc vào suy luận kiểu tại những tình huống phức tạp, ta cũng có thể **khai báo rõ** biến:

~~~java
ThrowingAction<java.io.IOException> ioTask =
        () -> { throw new java.io.IOException("Cannot read"); };

try {
    execute(ioTask);
} catch (java.io.IOException e) {
    System.out.println("Caught: " + e.getMessage());
}
~~~

Ở đây, `throws E` cho phép lan truyền checked `IOException`; **không có `catch(E)` nào được khai báo**.

### Tại sao `throws E` không mâu thuẫn với type erasure?

`throws E` là một phần của kiểm tra kiểu tĩnh và thông tin khai báo generic. Nó không yêu cầu JVM tạo handler runtime riêng dựa trên type argument.

Ngược lại, `catch (E e)` đặt `E` trực tiếp vào **điều kiện xử lý ngoại lệ**. Đó là thao tác mà Java không cho phép với type variable.

## 5. Dùng một kiểu class cụ thể thay cho `E`

Nếu generic method chỉ cần xử lý **mọi `IOException` hoặc subtype** và bound là `IOException`, bạn có thể bắt chính `IOException`:

~~~java
@FunctionalInterface
interface ReaderTask<E extends java.io.IOException> {
    String read() throws E;
}

static <E extends java.io.IOException> String withFallback(
        ReaderTask<E> task) {
    try {
        return task.read();
    } catch (java.io.IOException e) {
        return "fallback";
    }
}
~~~

Đây là mã hợp lệ nếu đặt trong một lớp Java. `E` có thể là `IOException` hoặc subtype; `catch(IOException)` bắt được những subtype đó. Không có lý do phải viết `catch(E)`.

Tuy nhiên, đổi `catch(E)` thành `catch(Exception)` không phải lúc nào cũng là một quyết định tốt. Handler rộng có thể bắt luôn những `RuntimeException` do lỗi lập trình hoặc trạng thái bất thường. Cần cân nhắc phạm vi lỗi mình thực sự muốn xử lý.

### Bắt theo upper bound: đúng nhưng có thể quá rộng

Ví dụ:

~~~java
static <E extends Exception> void inspect(
        ThrowingAction<E> action) {
    try {
        action.run();
    } catch (Exception caught) {
        System.out.println(caught.getClass().getSimpleName());
    }
}
~~~

Đây là mã Java hợp lệ. Nó nhận mọi `Exception` có thể thoát từ khối `try`, bao gồm cả unchecked `RuntimeException`.

Nếu mục tiêu chỉ là xử lý một nhóm lỗi cụ thể, hãy dùng upper bound hẹp hơn, overload chuyên biệt hoặc class token rõ ràng. Đừng bắt `Exception` rồi mặc định coi **mọi đối tượng bắt được** đều thuộc một subtype `E` nào đó.

## 6. Dùng `Class<E>` để kiểm tra subtype cụ thể khi thật sự cần

Giả sử ta viết một tiện ích generic nhận một tác vụ và muốn áp dụng fallback chỉ khi ngoại lệ đúng với một **lớp được caller truyền vào**.

Một hướng rõ ràng:

~~~java
static <E extends Exception> boolean matches(
        Throwable caught, Class<E> expectedType) {
    return expectedType.isInstance(caught);
}
~~~

Đây là một phương thức Java hợp lệ. `Class<E>` mang thông tin class runtime; `isInstance` làm phép kiểm tra. Nếu cần lấy biến kiểu `E` sau khi kiểm tra:

~~~java
static <E extends Exception> E castIfMatches(
        Throwable caught, Class<E> expectedType) {
    if (!expectedType.isInstance(caught)) {
        return null;
    }
    return expectedType.cast(caught);
}
~~~

Không nên tự viết ép kiểu `(E) caught` mà không kiểm tra, vì type erasure khiến compiler có thể cảnh báo unchecked cast và tính đúng đắn phụ thuộc dữ liệu runtime.

### Ưu điểm của class token

- Caller ghi rõ loại lỗi mong muốn, ví dụ `IOException.class`.
- `expectedType.isInstance(caught)` kiểm tra chính loại object ở runtime.
- `expectedType.cast(caught)` thực hiện checked cast theo token.
- Không cần `catch(E)` vốn bất hợp lệ.

### Giới hạn và trách nhiệm

- `Class<E>` chỉ đại diện một class runtime, **không biến type variable thành catch type**.
- Caller có thể truyền một class quá rộng như `Exception.class` và sẽ nhận nhiều loại lỗi hơn dự định.
- Nếu muốn chỉ khớp đúng class, dùng `caught.getClass() == expectedType`, không dùng `isInstance`. Tuy nhiên, trong xử lý exception thường muốn nhận cả subtype nên `isInstance` dễ phù hợp hơn.
- Nếu có nhiều loại checked exception, một `Class<E>` duy nhất không biểu diễn một hợp đồng đa lỗi trọn vẹn; cần thiết kế API riêng.
- Việc “đã match” chỉ cho biết **kiểu lỗi**, không tự quyết định retry/fallback có an toàn về nghiệp vụ hay không.

## 7. Một chương trình Java 17+ độc lập minh họa đầy đủ

Tạo tệp **`GenericCatchLimitDemo.java`**:

~~~java
import java.io.IOException;
import java.sql.SQLException;

public class GenericCatchLimitDemo {

    @FunctionalInterface
    interface ThrowingSupplier<T, E extends Exception> {
        T get() throws E;
    }

    @FunctionalInterface
    interface ThrowingAction<E extends Exception> {
        void run() throws E;
    }

    static <T, E extends Exception> T execute(
            ThrowingSupplier<T, E> supplier) throws E {
        return supplier.get();
    }

    static <E extends Exception> void executeAction(
            ThrowingAction<E> action) throws E {
        action.run();
    }

    static <T, E extends Exception> T fallbackOnType(
            ThrowingSupplier<T, E> supplier,
            Class<E> expectedType,
            T fallback) {
        try {
            return supplier.get();
        } catch (Exception caught) {
            if (expectedType.isInstance(caught)) {
                E typed = expectedType.cast(caught);
                System.out.println(
                        "matched=" + typed.getClass().getSimpleName()
                                + ": " + typed.getMessage());
                return fallback;
            }
            if (caught instanceof RuntimeException runtime) {
                throw runtime;
            }
            throw new IllegalStateException(
                    "Unexpected checked exception", caught);
        }
    }

    static <E extends IOException> String catchBound(
            ThrowingSupplier<String, E> supplier) {
        try {
            return supplier.get();
        } catch (IOException e) {
            System.out.println("bound=" + e.getMessage());
            return "bound-fallback";
        }
    }

    static void multiCatch(boolean io) {
        try {
            if (io) {
                throw new IOException("read error");
            }
            throw new SQLException("query error");
        } catch (IOException | SQLException e) {
            System.out.println(
                    "multi=" + e.getClass().getSimpleName()
                            + ": " + e.getMessage());
        }
    }

    public static void main(String[] args) {
        System.out.println("== generic throws ==");
        ThrowingSupplier<String, IOException> ioSupplier =
                () -> { throw new IOException("disk offline"); };

        try {
            execute(ioSupplier);
        } catch (IOException e) {
            System.out.println("caught=" + e.getMessage());
        }

        System.out.println("== generic lambda ==");
        ThrowingAction<SQLException> sqlAction =
                () -> { throw new SQLException("database offline"); };
        try {
            executeAction(sqlAction);
        } catch (SQLException e) {
            System.out.println("action=" + e.getMessage());
        }

        System.out.println("== class token ==");
        String recovered = fallbackOnType(
                ioSupplier, IOException.class, "default");
        System.out.println("result=" + recovered);

        System.out.println("== successful supplier ==");
        ThrowingSupplier<String, IOException> ok =
                () -> "ready";
        System.out.println(
                "result=" + fallbackOnType(
                        ok, IOException.class, "default"));

        System.out.println("== subtype bound ==");
        System.out.println("result=" + catchBound(ioSupplier));

        System.out.println("== runtime mismatch ==");
        ThrowingSupplier<String, IOException> runtimeTask =
                () -> { throw new IllegalArgumentException("bad state"); };
        try {
            fallbackOnType(
                    runtimeTask, IOException.class, "default");
        } catch (IllegalArgumentException e) {
            System.out.println("not-matched=" + e.getMessage());
        }

        System.out.println("== multi-catch classes ==");
        multiCatch(true);
        multiCatch(false);
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac GenericCatchLimitDemo.java
java GenericCatchLimitDemo
~~~

**Stdout xác định:**

~~~text
== generic throws ==
caught=disk offline
== generic lambda ==
action=database offline
== class token ==
matched=IOException: disk offline
result=default
== successful supplier ==
result=ready
== subtype bound ==
bound=disk offline
result=bound-fallback
== runtime mismatch ==
not-matched=bad state
== multi-catch classes ==
multi=IOException: read error
multi=SQLException: query error
~~~

### Phân tích `generic throws`

`ThrowingSupplier<String, IOException>` là một lambda có thể ném checked `IOException`. Phương thức `execute` khai báo `throws E`, nên có thể lan truyền lỗi này. Caller sử dụng `catch (IOException e)` — một kiểu exception **cụ thể**.

Không có `catch (E e)` trong `execute`. Sự generic nằm ở **hợp đồng của method và functional interface**, không nằm ở loại catch.

### Phân tích `generic lambda`

`ThrowingAction<SQLException>` có một abstract method `void run() throws SQLException` sau khi áp dụng type argument. Lambda ném `SQLException` và caller bắt `SQLException`.

Điều này cho thấy generic type parameter trong `throws` vẫn rất hữu ích để tổ chức các công việc ném checked exception, dù catch không dùng type parameter.

### Phân tích `class token`

`fallbackOnType` bắt bằng `catch(Exception)`, sau đó gọi `expectedType.isInstance(caught)`. Với token `IOException.class`, ngoại lệ thực sự là `IOException` nên check thành công, `Class.cast` hợp lệ và phương thức trả `"default"`.

**Lưu ý:** handler rộng có chính sách rõ: khi lỗi là một `RuntimeException` không khớp token, nó **ném lại**, không che lỗi bằng giá trị mặc định; khi xuất hiện checked exception khác token, code bọc thành `IllegalStateException` giữ cause. Chính sách này minh họa cách tránh nuốt lỗi ngoài nhóm mong đợi, không phải quy định mọi thư viện phải xử lý y hệt.

### Phân tích `catchBound`

`E extends IOException` nên nếu task ném checked `E`, `catch(IOException)` bao phủ nó. Cách làm này đơn giản hơn class token khi tất cả lỗi mà phương thức muốn xử lý đều thuộc cùng một họ exception đã biết.

### Phân tích `runtime mismatch`

Lambda được khai báo với `E = IOException` vẫn có thể ném unchecked `IllegalArgumentException` vì unchecked exceptions không cần nằm trong `throws`. `catch(Exception)` bắt được nó, nhưng `IOException.class.isInstance(...)` sai. Mã không thay đổi lỗi đó thành một fallback; nó ném lại và caller bắt đúng `IllegalArgumentException`.

### Phân tích multi-catch

`catch (IOException | SQLException e)` hợp lệ vì cả hai đều là class exception cụ thể và không có quan hệ subtype với nhau. Compiler vẫn biết lựa chọn catch type có thể dùng để lọc handler.

**Không thể thay một vế bằng `E`**, dù `E` có bound như `Exception` hoặc `IOException`.

## 8. Phản ví dụ không biên dịch: `catch(E e)` trong generic method

Xét:

~~~java
interface Task<E extends Exception> {
    void run() throws E;
}

static <E extends Exception> void handle(Task<E> task) {
    try {
        task.run();
    } catch (E e) {
        System.out.println(e.getMessage());
    }
}
~~~

**Đây là phản ví dụ cố ý không biên dịch**, không chép chung vào chương trình chạy được. Tham số `e` trong `catch` có kiểu `E` là **type variable**. Compiler từ chối dù `E extends Exception`.

Có thể sửa theo ý định:

**Phương án A — Không xử lý tại đây:**

~~~java
static <E extends Exception> void propagate(Task<E> task) throws E {
    task.run();
}
~~~

**Phương án B — Xử lý toàn bộ nhóm `Exception` với chính sách cụ thể:**

~~~java
static <E extends Exception> void logAndWrap(Task<E> task) {
    try {
        task.run();
    } catch (Exception e) {
        throw new IllegalStateException("Task failed", e);
    }
}
~~~

**Phương án C — Thu hẹp bound về họ đã biết:**

~~~java
static <E extends IOException> void handleIO(
        ThrowingAction<E> task) {
    try {
        task.run();
    } catch (IOException e) {
        System.out.println("I/O: " + e.getMessage());
    }
}
~~~

Các ví dụ A/B giả định `Task` tồn tại, và phương án C giả định `ThrowingAction` có khai báo `throws E` như chương trình chính. Bản chất của ba hướng:

- A bảo toàn **checked contract `throws E`**.
- B chủ động chuyển lỗi sang unchecked wrapper **giữ cause**.
- C xử lý một lớp exception cụ thể đã biết qua upper bound.

Không nên chuyển `catch(E)` thành `catch(Throwable)` một cách máy móc. Bắt cả `Error` sẽ thay đổi đáng kể trách nhiệm của handler, và có thể che những sự cố nghiêm trọng nếu code chỉ log rồi tiếp tục.

## 9. Multi-catch và type parameter

Java 7+ hỗ trợ multi-catch:

~~~java
try {
    perform();
} catch (IOException | SQLException e) {
    log(e);
}
~~~

Đây là **mảnh minh họa**, `perform` có thể ném hai loại checked exception và `log` là hàm phù hợp.

Các alternative như `IOException` và `SQLException` phải là các loại exception hợp lệ. Một số quy tắc khác của multi-catch vẫn có hiệu lực: ví dụ không được kết hợp hai alternative có quan hệ subtype với nhau như `IOException | Exception`.

Type variable không thể làm một alternative:

~~~java
static <E extends Exception> void invalidMulti(
        ThrowingAction<E> task) throws E {
    try {
        task.run();
    } catch (E | RuntimeException e) { // KHÔNG BIÊN DỊCH.
        System.out.println(e);
    }
}
~~~

Mã này **cố ý sai**. Vế `E` vẫn là type variable, không hợp lệ làm catch type. Việc có thêm `RuntimeException` không sửa quy tắc.

### Type của biến multi-catch không phải type parameter chung

Ví dụ `catch (IOException | SQLException e)` làm biến `e` có kiểu được compiler suy ra theo quy tắc union catch (common supertype phù hợp để truy cập các thành viên chung). Điều đó không đồng nghĩa khai báo một type variable `E` rồi chọn subtype cụ thể theo từng lần gọi.

Tham số multi-catch được xem là **implicitly final** trong phạm vi tương ứng; không thể gán lại `e`. Đây là quy tắc khác với việc cấm `catch(E)` và không nên trộn lẫn hai nguyên nhân biên dịch.

## 10. Một lớp generic kế thừa `Throwable` cũng không hợp lệ

Java còn có một giới hạn liên quan: **không được tạo generic class là subtype của `Throwable`**.

Phản ví dụ:

~~~java
class TypedFailure<T> extends Exception {
    private final T value;

    TypedFailure(T value) {
        this.value = value;
    }
}
~~~

**Mã trên không biên dịch** vì generic class không được là subtype của `Throwable`. Điều này đúng ngay cả khi lớp kế thừa `Exception` hoặc `RuntimeException` thay vì `Throwable` trực tiếp.

Không thể dùng `TypedFailure<String>` và `TypedFailure<Integer>` như hai loại exception riêng biệt để catch ở runtime, bởi thông tin tham số kiểu không được biểu diễn thành các exception class có kiểu khác nhau ở runtime.

### Giải pháp: exception không generic, phương thức xử lý có thể generic

Ví dụ:

~~~java
final class ValidationFailure extends Exception {
    private final String field;

    ValidationFailure(String field, String message) {
        super(message);
        this.field = field;
    }

    String field() {
        return field;
    }
}

static <T> T validateNotNull(T value)
        throws ValidationFailure {
    if (value == null) {
        throw new ValidationFailure(
                "value", "value must not be null");
    }
    return value;
}
~~~

Các khai báo có thể đặt trong một lớp Java. `ValidationFailure` không generic; phương thức `validateNotNull` vẫn có type parameter `T`, bảo toàn kiểu giá trị trả về khi thành công.

Nếu cần dữ liệu lỗi có cấu trúc, dùng mã lỗi, enum, tên trường hoặc metadata thích hợp, thay vì generic type argument trên chính exception class.

### Exception có phương thức generic thì sao?

Một **lớp exception không generic** vẫn có thể định nghĩa một số phương thức generic thông thường, miễn là chúng phù hợp quy tắc Java. Điều bị cấm là **lớp exception bản thân mang type parameter** như `MyException<T> extends Exception`, không phải mọi cách sử dụng generic trong code liên quan đến exception.

## 11. Lambda và checked exception: target type mới là hợp đồng

Một lambda không tự mang một chữ ký `throws` độc lập. Quy tắc checked exception của nó phụ thuộc vào **functional interface** được dùng làm target type.

Ví dụ `java.util.function.Function<T,R>` có phương thức:

~~~java
R apply(T value);
~~~

Nó không khai báo `throws IOException`. Vì vậy mảnh sau **không biên dịch** khi `Files.readString` có thể ném checked `IOException`:

~~~java
java.util.function.Function<String, String> readText =
        path -> java.nio.file.Files.readString(
                java.nio.file.Path.of(path));
~~~

Có thể giải quyết theo ba hướng tùy hợp đồng.

### Hướng A — Bắt và chuyển thành unchecked wrapper

~~~java
java.util.function.Function<String, String> readText =
        path -> {
            try {
                return java.nio.file.Files.readString(
                        java.nio.file.Path.of(path));
            } catch (IOException cause) {
                throw new java.io.UncheckedIOException(
                        "Cannot read file", cause);
            }
        };
~~~

Đây là đoạn minh họa cần import `IOException` hoặc dùng tên đầy đủ. `UncheckedIOException` là một unchecked exception chuẩn có thể giữ `IOException` làm cause.

Hướng này phù hợp khi API tiếp nhận `Function` không cho checked exception thoát và bên gọi được thiết kế xử lý unchecked wrapper.

### Hướng B — Dùng functional interface có `throws E`

~~~java
@FunctionalInterface
interface CheckedFunction<T, R, E extends Exception> {
    R apply(T value) throws E;
}
~~~

Caller:

~~~java
CheckedFunction<String, String, IOException> readText =
        path -> java.nio.file.Files.readString(
                java.nio.file.Path.of(path));
~~~

Lambda có thể ném checked `IOException` vì `apply` của target type khai báo `throws E` và `E` được chọn là `IOException`. Một phương thức sử dụng nó có thể khai báo `throws E` tương ứng.

### Hướng C — Dùng API khác phản ánh thất bại như kết quả

Nếu “không đọc được” là một nhánh dự kiến mà caller luôn phải xử lý, có thể cân nhắc một `Result` type với hai trạng thái hoặc API cung cấp fallback có kiểm soát.

Không có một lựa chọn duy nhất cho mọi dự án. Quan trọng là **hợp đồng exception của functional interface**, không phải suy luận “lambda không hỗ trợ checked exceptions”.

### Liên hệ với `catch(E)`

Ngay cả khi target type có `throws E`:

~~~java
static <T, R, E extends Exception> R applyChecked(
        CheckedFunction<T, R, E> fn, T input) throws E {
    return fn.apply(input);
}
~~~

đây là code hợp lệ. Nhưng nếu phương thức muốn tự bắt lỗi:

~~~java
static <T, R, E extends Exception> R broken(
        CheckedFunction<T, R, E> fn, T input) {
    try {
        return fn.apply(input);
    } catch (E e) { // Không hợp lệ.
        return null;
    }
}
~~~

Giới hạn của `catch(E)` vẫn áp dụng. Type variable làm phần `throws` được, nhưng không làm type của catch parameter.

## 12. Phân biệt overload, subtype và token trong API xử lý lỗi

Giả sử thư viện có hai chiến lược xử lý:

- Một phương thức chỉ xử lý `IOException`.
- Một phương thức chỉ xử lý `SQLException`.

Đôi khi **overload chuyên biệt** làm API dễ hiểu hơn một generic handler phức tạp.

~~~java
static String fromIO(ThrowingSupplier<String, IOException> fn) {
    try {
        return fn.get();
    } catch (IOException e) {
        return "I/O fallback";
    }
}
~~~

Một API SQL có thể dùng functional interface và method riêng cho SQL. Tuy nhiên do type erasure, **không thể giả định hai overload chỉ khác `ThrowingSupplier<String, IOException>` và `ThrowingSupplier<String, SQLException>` sẽ có chữ ký runtime khác nhau**: chúng có cùng raw type và có thể gây *name clash* khi trùng tên method.

Hãy dùng tên phương thức rõ ràng, interface khác nhau hoặc thêm tham số phân biệt nếu thực sự cần overload.

### Token không tự làm typed catch

Ngay cả khi method nhận `Class<E> expectedType`, đoạn này vẫn sai:

~~~java
static <E extends Exception> void wrongTokenCatch(
        Class<E> expectedType, ThrowingAction<E> task) {
    try {
        task.run();
    } catch (E e) { // Vẫn lỗi biên dịch.
        System.out.println(e);
    }
}
~~~

`Class<E>` chỉ giúp **kiểm tra động sau khi bắt bằng kiểu hợp lệ**. Nó không thay đổi ngữ pháp hoặc luật type checking của `catch`.

## 13. Bắt rộng có thể che lỗi lập trình

Giả sử code generic làm:

~~~java
static <E extends Exception> String unsafeFallback(
        ThrowingSupplier<String, E> supplier) {
    try {
        return supplier.get();
    } catch (Exception ignored) {
        return "default";
    }
}
~~~

Đây là một phương thức hợp lệ nhưng **chỉ nên áp dụng khi chính sách fallback cho mọi `Exception` là hợp lệ**. Vì `RuntimeException extends Exception`, những lỗi như `NullPointerException` hoặc `IllegalArgumentException` cũng bị nuốt.

Khi lỗi chỉ nên được phục hồi nếu đúng một lớp được dự kiến, dùng:

- `catch(IOException)` khi hợp đồng đã hẹp tới I/O; hoặc
- `Class<E>.isInstance` cùng một chính sách rõ cho lỗi không khớp.

Đừng suy ra rằng **vì `E extends Exception` nên mọi `Exception` bắt được đều đúng loại `E`**. Một lambda có thể ném unchecked exception không được liệt kê trong `throws E`.

## 14. Vì sao không nên dùng ép kiểu `(E) e` bừa bãi?

Giả sử:

~~~java
static <E extends Exception> E unsafeCast(Exception e) {
    return (E) e;
}
~~~

Đây là phản ví dụ có thể biên dịch với **cảnh báo unchecked cast** tùy ngữ cảnh compiler. Vì type erasure, câu lệnh cast không bảo đảm kiểm tra đúng type argument mong muốn tại thời điểm ấy.

Một caller có thể tưởng mình nhận `IOException` nhưng đối tượng thực tế lại là subtype `Exception` khác. Lỗi có thể chỉ xuất hiện muộn khi giá trị bị ép lại ở điểm sử dụng.

Hướng an toàn hơn:

~~~java
static <E extends Exception> E checkedCast(
        Exception e, Class<E> expectedType) {
    return expectedType.cast(e);
}
~~~

`Class.cast` kiểm tra class runtime và ném `ClassCastException` nếu đối tượng không phù hợp. Nếu muốn tránh ném khi không khớp, kiểm tra `isInstance` trước.

**Không nên dùng reflection làm mọi nơi chỉ để thay generic exception handling.** Nếu chỉ có một nhóm lỗi được xử lý, `catch(IOException)` hoặc `catch(SQLException)` thường đơn giản hơn.

## 15. `E extends Throwable` có khác `E extends Exception` không?

Có thể khai báo:

~~~java
static <E extends Throwable> void throwAny(E failure) throws E {
    throw failure;
}
~~~

Đây là Java hợp lệ. Type parameter `E` có bound `Throwable` nên được dùng ở `throws` và `throw`.

Nhưng:

~~~java
static <E extends Throwable> void cannotCatchE(
        E failure) {
    try {
        throw failure;
    } catch (E caught) { // KHÔNG BIÊN DỊCH.
        System.out.println(caught);
    }
}
~~~

Vẫn sai. Nới bound từ `Exception` lên `Throwable` không làm `catch(E)` hợp lệ.

Thêm nữa, `catch(Throwable)` sẽ bắt cả những đối tượng thuộc nhánh `Error`. Đây là trách nhiệm rộng, cần chính sách rất đặc biệt nếu sử dụng tại ranh giới runtime/framework. Trong code nghiệp vụ thông thường, bắt `Exception` hoặc lớp hẹp hơn thường phù hợp hơn.

### `E extends RuntimeException` cũng không cứu được `catch(E)`

~~~java
static <E extends RuntimeException> void bad(
        E failure) {
    try {
        throw failure;
    } catch (E e) { // Vẫn lỗi compile-time.
        System.out.println(e);
    }
}
~~~

Cho dù `E` chắc chắn unchecked, nó vẫn là type variable. **Checked/unchecked khác với yêu cầu type của catch parameter**; không thể dùng một quy tắc để xóa quy tắc còn lại.

## 16. Generic method có thể mô tả chính xác checked exception của caller

Ví dụ một chuỗi xử lý hai bước cùng khai báo khả năng ném `E`:

~~~java
@FunctionalInterface
interface CheckedStep<E extends Exception> {
    void run() throws E;
}

static <E extends Exception> void runBoth(
        CheckedStep<E> first,
        CheckedStep<E> second) throws E {
    first.run();
    second.run();
}
~~~

Đây là code hợp lệ. Trong trường hợp caller dùng `CheckedStep<IOException>` ở cả hai bước, `runBoth` có thể ném checked `IOException` theo hợp đồng.

Tuy nhiên, nếu hai bước có hai loại checked exception khác nhau, việc ép cả hai về một `E` có thể làm mất thông tin tĩnh cụ thể hoặc buộc suy luận một common supertype. Có thể thiết kế hai type parameter:

~~~java
static <E1 extends Exception, E2 extends Exception>
void runTwoKinds(
        CheckedStep<E1> first,
        CheckedStep<E2> second) throws E1, E2 {
    first.run();
    second.run();
}
~~~

Đoạn này hợp lệ. Caller phải xử lý những checked exceptions tương ứng theo cách sử dụng.

Điểm chính: **generic throws rất linh hoạt**, nhưng khi muốn tự bắt trong phương thức này, vẫn phải dùng catch type hợp lệ, ví dụ `catch(IOException)` khi biết trước lớp, `catch(Exception)` khi chính sách cho phép, hoặc một cơ chế kiểm tra động có thiết kế riêng.

## 17. Những lỗi biên dịch phổ biến cần nhận diện

### 17.1. `catch(E e)`

~~~java
static <E extends Exception> void f(ThrowingAction<E> action) {
    try {
        action.run();
    } catch (E e) { }
}
~~~

Sai vì **catch parameter type là type variable**.

### 17.2. `catch(E | IOException e)`

~~~java
static <E extends Exception> void f(ThrowingAction<E> action) {
    try {
        action.run();
    } catch (E | IOException e) { }
}
~~~

Sai vì `E` không được dùng làm multi-catch alternative.

### 17.3. `class Problem<T> extends Exception`

~~~java
class Problem<T> extends Exception {
}
~~~

Sai vì **generic class không được là subtype của `Throwable`**.

### 17.4. `new E()`

~~~java
static <E extends Exception> E make() {
    return new E();
}
~~~

Sai vì không thể tạo instance trực tiếp từ type variable.

### 17.5. `instanceof E`

~~~java
static <E extends Exception> boolean matches(
        Throwable thrown) {
    return thrown instanceof E;
}
~~~

Sai vì type variable không phải một reifiable runtime type thích hợp cho phép kiểm tra `instanceof`.

Các lỗi 17.4 và 17.5 không riêng về `catch`, nhưng đến từ cùng một ý tưởng sai: tưởng rằng compiler có một class object runtime độc lập tương ứng với type variable `E`.

### 17.6. Lambda ném checked exception vào `Function` chuẩn

~~~java
java.util.function.Function<String, String> read =
        path -> java.nio.file.Files.readString(
                java.nio.file.Path.of(path));
~~~

Sai vì `Function.apply` không có checked `throws IOException`.

### 17.7. Multi-catch hai loại có quan hệ subtype

~~~java
try {
    something();
} catch (IOException | Exception e) {
    System.out.println(e);
}
~~~

Sai vì `IOException` là subtype của `Exception`. Đây là quy tắc **khác** với type variable, nhưng thường xuất hiện khi người học cố thay thế `catch(E)` bằng một union rộng quá mức.

## 18. FAQ về cách xử lý type parameter và exception

**Hỏi: Có thể dùng `catch (T e)` nếu `T extends IOException` không?**  
Không. `T` vẫn là type variable; bắt `IOException` nếu muốn xử lý cả họ I/O.

**Hỏi: Có thể dùng `catch (E e)` nếu method nhận `Class<E>` không?**  
Không. Token chỉ giúp kiểm tra **bên trong một catch hợp lệ** hoặc code xử lý bình thường.

**Hỏi: `throws E` có cần `E extends Exception` không?**  
Không nhất thiết; upper bound `Throwable` hoặc subtype thích hợp cũng được. Ví dụ `<E extends Throwable> ... throws E` là hợp lệ.

**Hỏi: Vì sao `catch (Exception e)` hợp lệ nhưng `catch (E e)` không?**  
`Exception` là một class exception có thể dùng cho handler. `E` là type variable, bị cấm làm catch parameter type.

**Hỏi: Generic class có thể khai báo phương thức throws một type parameter không?**  
Có, nếu tham số kiểu có bound phù hợp. Ví dụ một generic functional interface với `E extends Exception` có thể có `run() throws E`.

**Hỏi: Java có generic exception class như `MyException<T>` không?**  
Không, nếu class ấy kế thừa `Throwable` trực tiếp hoặc gián tiếp. Hãy dùng exception class không generic, rồi giữ metadata hoặc dùng generic method bên ngoài.

**Hỏi: `IOException.class` có bắt cả subtype `FileNotFoundException` không?**  
Có, nếu dùng `Class.isInstance`; đây là phép kiểm tra tương ứng quan hệ subtype tại runtime.

**Hỏi: Dùng `getClass() == expectedType` thì sao?**  
Chỉ khớp class **chính xác**, không nhận subtype. Chọn hành vi theo hợp đồng.

**Hỏi: Có nên luôn bắt `Exception` rồi check `Class<E>` không?**  
Không. Nếu class cần xử lý đã biết, `catch` kiểu cụ thể dễ đọc, rõ trách nhiệm và ít rủi ro hơn.

**Hỏi: Một lambda khai báo `ThrowingSupplier<T,IOException>` có thể vẫn ném `NullPointerException` không?**  
Có. Unchecked exception không bị giới hạn chỉ vào checked `throws IOException`. Vì vậy handler rộng không nên mặc định mọi lỗi bắt được đều thuộc `IOException`.

**Hỏi: `catch(Throwable)` có giải quyết giới hạn này không?**  
Về cú pháp là handler hợp lệ, nhưng phạm vi rất rộng gồm cả `Error`. Nó không tương đương bắt chính xác `E` và không nên là cách thay thế mặc định.

**Hỏi: Vì sao cần bảo toàn cause khi bọc lỗi trong generic helper?**  
Để không mất thông tin lỗi gốc và stack trace. Dùng constructor `new IllegalStateException("...", caught)`, không chỉ nối `caught.getMessage()` thành chuỗi.

## 19. Kiểm tra kiến thức

1. Vì sao `catch (E e)` không hợp lệ khi `E extends Exception`?
2. `throws E` có hợp lệ với `E extends Exception` không?
3. `throw error;` với biến `error` kiểu `E extends Exception` có hợp lệ không?
4. `catch (IOException e)` có bắt một subtype của `IOException` không?
5. Nếu `E extends IOException`, có thể dùng `catch(E)` không?
6. `catch (Exception e)` trong generic method có thể bắt cả unchecked `RuntimeException` không?
7. Vì sao type erasure liên quan tới việc không thể dùng `E` làm catch type?
8. `Class<E>` cho phép hai thao tác nào để kiểm tra và cast an toàn?
9. `Class.isInstance` có nhận subclass không?
10. Vì sao không nên luôn trả fallback sau bất kỳ `Exception` nào?
11. Dạng khai báo `<E extends Throwable> void f() throws E` có hợp lệ không?
12. Vì sao `class MyException<T> extends Exception` không biên dịch?
13. Có thể dùng type parameter trong `throws` của generic functional interface không?
14. `Function<T,R>` chuẩn có cho lambda tự ném checked `IOException` ra ngoài không?
15. Nếu muốn lambda ném checked `IOException`, nên thay target interface như thế nào?
16. `catch (IOException | SQLException e)` có hợp lệ khi hai lỗi có thể ném không?
17. `catch (IOException | Exception e)` vì sao sai?
18. `catch (E | IOException e)` vì sao sai?
19. Một `ThrowingSupplier<String,IOException>` có thể ném unchecked `IllegalArgumentException` không?
20. `catch(Throwable)` có ý nghĩa giống `catch(E)` không?
21. `(E) exception` có kiểm tra chắc chắn đúng type argument runtime không?
22. Khi nào nên ưu tiên catch class cụ thể thay cho token?
23. `throws E1, E2` trong method có hai type parameter bounded là hợp lệ không?
24. Một exception class không generic có thể được ném từ generic method không?
25. Nếu chỉ cần ghi lại lỗi rồi chuyển tiếp, có nhất thiết phải tự viết catch generic không?

### Đáp án gợi ý

1. Vì type variable không được dùng làm loại tham số của catch clause.
2. Có.
3. Có.
4. Có.
5. Không; dùng `catch(IOException)` nếu phù hợp.
6. Có.
7. Type argument generic không tạo ra class handler runtime riêng cho mỗi instantiation.
8. `isInstance` và `cast`.
9. Có.
10. Vì có thể che lỗi lập trình/unchecked hoặc lỗi không có fallback an toàn.
11. Có, trong một cấu trúc khai báo hợp lệ.
12. Generic class không được kế thừa `Throwable` trực tiếp/gián tiếp.
13. Có, ví dụ `void run() throws E`.
14. Không; `Function.apply` không khai báo checked exception.
15. Dùng interface riêng có `throws E` hoặc bắt và wrap theo hợp đồng.
16. Có.
17. Vì hai alternative có quan hệ subtype.
18. Vì `E` là type variable.
19. Có, unchecked exception không buộc khai báo.
20. Không; `Throwable` bắt cả lỗi khác ngoài phạm vi `E`, kể cả `Error`.
21. Không; có thể chỉ là unchecked cast do type erasure.
22. Khi loại lỗi đã biết tại nơi viết handler.
23. Có, với bound phù hợp và xử lý checked exception ở caller.
24. Có.
25. Không; có thể dùng `throws E` và để caller xử lý, hoặc bắt loại cụ thể khi cần.

## 20. Ghi nhớ

**Trong Java Generic, `throws E` được phép còn `catch (E e)` bị cấm nếu `E` là type parameter.** Upper bound `E extends Exception`, `E extends IOException` hay `E extends RuntimeException` đều không biến `E` thành một kiểu catch hợp lệ. Hãy dùng `catch` với **class exception cụ thể** khi biết nhóm lỗi, dùng `throws E` để giữ hợp đồng checked exception của generic method/functional interface, và chỉ dùng `Class<E>.isInstance/cast` khi thực sự cần so khớp một loại lỗi do caller chỉ định tại runtime. Đồng thời tránh định nghĩa generic exception class kế thừa `Throwable`; hãy giữ exception type không generic và đặt sự linh hoạt vào method hoặc interface.