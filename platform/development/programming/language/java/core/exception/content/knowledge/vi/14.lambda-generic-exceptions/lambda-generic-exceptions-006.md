# Phương thức generic có tham số kiểu mở rộng `Throwable` trong Java

## 1. Vấn đề đặt ra

Java cho phép khai báo một **type parameter** trong phương thức generic với ràng buộc trên là `Throwable`:

```java
static <E extends Throwable> void propagate(E failure) throws E {
    throw failure;
}
```

Ở đây, `E` không phải tên một lớp ngoại lệ cụ thể. Nó là **tham số kiểu** được suy ra hoặc chỉ định khi gọi phương thức. Điều kiện `E extends Throwable` bảo đảm mọi kiểu thực dùng thay `E` là `Throwable` hoặc một lớp con của nó, do đó đối tượng có thể được ném bằng `throw` và xuất hiện trong mệnh đề `throws E`.

Một số tình huống cần tính năng này: helper muốn truyền lại **đúng loại ngoại lệ** của caller; functional interface có phương thức ném checked exception; API callback generic muốn chuyển tiếp ngoại lệ mà không ép mọi người gọi phải xử lý một `Exception` quá rộng.

Tuy nhiên, vì `E` là type variable, Java có những giới hạn quan trọng: không thể `catch (E e)`, không thể `new E()`, và hệ thống kiểm tra checked exception phải dựa trên **ràng buộc kiểu cùng ngữ cảnh suy luận**. Không nên dùng generic `throws E` chỉ như mẹo “qua mặt” checked exception.

Mục tiêu:

- Phân biệt `<E extends Throwable>`, `throws E` và `throw expression`.
- Hiểu ý nghĩa của ràng buộc `Throwable`, `Exception`, `RuntimeException` và các kiểu con cụ thể.
- Tạo phương thức generic giữ kiểu ngoại lệ khi truyền tiếp, với ví dụ checked và unchecked.
- Xây một functional interface có tham số kiểu ngoại lệ để dùng lambda ném checked exception.
- Xác định nghĩa vụ `try/catch` hoặc `throws` ở caller qua kiểu generic đã được suy ra/chỉ định.
- Hiểu tại sao `catch (E e)` và `new E()` không hợp lệ.
- Biết cách dựng ngoại lệ qua factory thay vì tạo trực tiếp từ type variable.
- Nắm giới hạn khi phương thức generic được override, phương thức functional interface được chuyên biệt hóa, và khi dùng `Runnable`/`Function` chuẩn.
- Nhận biết rủi ro của *sneaky throw*, unchecked cast và suy luận type parameter ở `throws`.

Tất cả chương trình hoàn chỉnh bên dưới được thiết kế cho **Java 17+**, có lệnh `javac`/`java` và kết quả `stdout` chính xác. Đoạn không độc lập và ví dụ cố ý sai được ghi rõ.

## 2. Đọc đúng cú pháp generic `throws`

Xét:

```java
public static <E extends Throwable> void rethrow(E error) throws E {
    throw error;
}
```

Hãy tách thành ba thành phần:

| Cú pháp | Ý nghĩa |
| --- | --- |
| `<E extends Throwable>` | Khai báo tham số kiểu `E` với upper bound `Throwable` |
| `E error` | Tham số phương thức có kiểu tĩnh là type variable `E` |
| `throws E` | Khai báo phương thức có thể truyền một ngoại lệ mang kiểu `E` |
| `throw error;` | Thực hiện ném **đối tượng** mà biến `error` đang tham chiếu |

Dấu `extends` trong **type parameter bound** cho phép chọn các lớp con thích hợp của `Throwable`. Nó **không phải** câu lệnh `throw` và cũng không có nghĩa “bắt mọi throwable”.

Ví dụ khi caller truyền một biến có kiểu tĩnh `IOException`:

```java
java.io.IOException failure = new java.io.IOException("disk failed");
rethrow(failure);
```

Đây là mảnh mã đặt trong một phương thức thích hợp. Compiler có thể suy ra `E = IOException` trong lời gọi trên. Vì vậy lời gọi có nghĩa vụ checked exception `IOException`: phải bắt hoặc khai báo nếu đang ở ngữ cảnh yêu cầu.

Nếu caller truyền `new IllegalArgumentException(...)`, kiểu ngoại lệ được truyền là unchecked; không bắt buộc ghi `throws` ở caller.

### Quan trọng: upper bound không biến đối tượng thành một `Throwable` mới

`rethrow(E error)` ném **chính đối tượng** mà nó nhận, không tạo một ngoại lệ khác. Các trường như message, cause, stack trace và suppressed exceptions đang nằm trên đối tượng đó được giữ nguyên. Type parameter chỉ là công cụ kiểm tra kiểu ở compile time.

## 3. `Throwable`, `Exception` và `RuntimeException` trong generic bound

Một cây kiểu rút gọn:

```text
Throwable
├── Error                       [unchecked]
│   └── AssertionError
└── Exception
    ├── IOException             [checked]
    │   └── FileNotFoundException
    ├── SQLException            [checked]
    └── RuntimeException        [unchecked]
        ├── IllegalArgumentException
        └── IllegalStateException
```

Đây không phải toàn bộ hệ phân cấp Java, chỉ các kiểu cần để hiểu ràng buộc.

Các khai báo generic:

```java
static <E extends Throwable> void a(E failure) throws E {
    throw failure;
}

static <E extends Exception> void b(E failure) throws E {
    throw failure;
}

static <E extends RuntimeException> void c(E failure) throws E {
    throw failure;
}

static <E extends java.io.IOException> void d(E failure) throws E {
    throw failure;
}
```

Đây là **bốn phương thức minh họa hợp lệ**, đặt trong một class Java. Chúng không có cùng phạm vi kiểu:

- `E extends Throwable` cho phép `IOException`, `RuntimeException`, `Error` hoặc chính `Throwable` và các lớp con thích hợp.
- `E extends Exception` loại bỏ nhánh `Error`, nhưng **vẫn gồm** checked exception và các subclass của `RuntimeException`.
- `E extends RuntimeException` giới hạn về nhánh unchecked, do đó các ngoại lệ thuộc `E` không tạo nghĩa vụ checked exception ở caller.
- `E extends IOException` giới hạn vào các kiểu checked I/O, như `IOException` và `FileNotFoundException`.

**Không được suy ra “mọi `E extends Exception` đều checked”.** `RuntimeException` là con của `Exception` nhưng unchecked.

Tương tự, **`E extends Throwable` không buộc mọi lời gọi đều phải bắt `Throwable`**. Nghĩa vụ có thể cụ thể hơn khi `E` được suy ra hoặc được chỉ định; nếu kiểu tĩnh của lời gọi đúng là `Throwable`, caller có thể phải xử lý/khai báo phạm vi rộng ấy.

## 4. Chương trình hoàn chỉnh: ném lại đúng loại đã truyền

Tạo tệp **`GenericRethrowDemo.java`**:

```java
import java.io.IOException;

public class GenericRethrowDemo {
    static <E extends Throwable> void rethrow(E failure) throws E {
        throw failure;
    }

    public static void main(String[] args) {
        IOException io = new IOException("disk offline");

        try {
            rethrow(io);
        } catch (IOException failure) {
            System.out.println("checked=" + failure.getMessage());
        }

        try {
            rethrow(new IllegalArgumentException("bad argument"));
        } catch (IllegalArgumentException failure) {
            System.out.println("unchecked=" + failure.getMessage());
        }

        try {
            rethrow(new AssertionError("broken invariant"));
        } catch (AssertionError failure) {
            System.out.println("error=" + failure.getMessage());
        }
    }
}
```

Biên dịch và chạy:

```bash
javac GenericRethrowDemo.java
java GenericRethrowDemo
```

`stdout`:

```text
checked=disk offline
unchecked=bad argument
error=broken invariant
```

Phân tích:

1. Lời gọi `rethrow(io)` có đối số kiểu `IOException`, nên kiểu generic phù hợp là checked exception này. `catch (IOException)` xử lý.
2. `IllegalArgumentException` là unchecked, vẫn được ném đúng đối tượng đó, không bắt buộc khai báo `throws`.
3. `AssertionError` cũng thuộc `Throwable` nhưng qua nhánh `Error` và unchecked. Ví dụ chủ ý bắt ngay tại `main` để minh họa kiểu; ứng dụng thông thường **không nên coi mọi Error là có thể phục hồi**.

Phương thức `rethrow` không tạo ngoại lệ mới, không chuyển checked thành unchecked và không đổi nguyên nhân gốc. Nó đơn thuần cho phép phương thức generic khai báo một loại lỗi gắn với tham số kiểu của chính lời gọi.

### Kiểu tĩnh của đối số ảnh hưởng nghĩa vụ xử lý

Nếu biến được khai báo là `Throwable` mặc dù runtime đang chứa `IOException`:

```java
Throwable failure = new java.io.IOException("disk");
rethrow(failure);
```

Đây là mảnh mã. Compiler nhìn thấy type argument có thể là `Throwable`, nên ngữ cảnh gọi phải xử lý/khai báo kiểu phù hợp với `Throwable`, trừ khi có ngữ cảnh suy luận khác hợp lệ. Java không suy luận chắc chắn `IOException` chỉ dựa trên một đối tượng runtime.

Để giữ thông tin checked exception cụ thể khi API cần, đừng tùy tiện đổi mọi tham số thành `Throwable`. Hợp đồng generic phụ thuộc **kiểu biểu thức tại compile time**.

## 5. Tại sao phải có `throws E` nếu đã có `E extends Throwable`?

Ràng buộc kiểu chỉ chứng minh rằng `E` là loại có thể ném; nó **không tự khai báo** phương thức sẽ truyền checked exception ra ngoài. Ví dụ mã sau là **cố ý không biên dịch**:

```java
static <E extends Throwable> void broken(E failure) {
    throw failure; // Compiler có thể yêu cầu khai báo/bắt E.
}
```

Vì `E` có thể là `IOException` hoặc một checked `Throwable` khác, phương thức không được bỏ qua nghĩa vụ. Cần khai báo:

```java
static <E extends Throwable> void valid(E failure) throws E {
    throw failure;
}
```

Nếu thay `E extends RuntimeException`, ngoại lệ được ném là unchecked:

```java
static <E extends RuntimeException> void validUnchecked(E failure) {
    throw failure;
}
```

Đây là ví dụ hợp lệ về ràng buộc chặt hơn, không bắt buộc có `throws E`. Dù vậy, có thể viết `throws E` để mô tả API; nó không biến exception unchecked thành checked.

### `throws E` và `throws Throwable` không luôn tương đương

`throws Throwable` công bố một loại rất rộng cho mọi caller. `throws E` có thể cung cấp mối liên hệ chính xác giữa kiểu ngoại lệ của tham số hoặc callback và trách nhiệm của caller. Đây là giá trị lớn của generic exception type: **không mở rộng vô cớ hợp đồng lỗi**.

Nhưng khi `E` chỉ bị ràng buộc bởi `Throwable` và không thể suy luận hẹp, compiler có thể vẫn phải kiểm tra một loại ngoại lệ rộng. Generic không bảo đảm hợp đồng luôn hẹp; việc lựa chọn type argument và chữ ký API mới là yếu tố quyết định.

## 6. Lambda có checked exception: cần functional interface phù hợp

Các functional interface phổ biến của Java như `Runnable` hoặc `java.util.function.Function<T,R>` **không khai báo checked exception** trong phương thức abstract của chúng. Vì thế, không thể trực tiếp ném `IOException` không được xử lý từ thân lambda gán vào `Runnable`:

```java
Runnable task = () -> {
    throw new java.io.IOException("cannot read"); // KHÔNG BIÊN DỊCH.
};
```

Đây là ví dụ **cố ý không biên dịch**. `Runnable.run()` không có `throws IOException`.

Một giải pháp thiết kế đúng là khai báo **functional interface của riêng ứng dụng** có type parameter ngoại lệ:

```java
@FunctionalInterface
interface ThrowingAction<E extends Throwable> {
    void run() throws E;
}
```

Sau đó tạo phương thức generic gọi callback:

```java
static <E extends Throwable> void execute(ThrowingAction<E> action)
        throws E {
    action.run();
}
```

Hai mảnh khai báo này hợp lệ. Chúng giữ quan hệ:

```text
ThrowingAction<IOException>
          |
          v
execute(action) throws IOException
          |
          v
caller catch IOException / throws IOException
```

Kiểu `E` không nhất thiết phải luôn là `Throwable`; nếu API chỉ cần checked/unchecked thuộc `Exception` và không muốn nhận `Error` như một lựa chọn thiết kế, có thể chọn `E extends Exception`.

## 7. Chương trình hoàn chỉnh: lambda ném `IOException` qua generic helper

Tạo tệp **`GenericLambdaThrowsDemo.java`**:

```java
import java.io.IOException;

public class GenericLambdaThrowsDemo {
    @FunctionalInterface
    interface ThrowingSupplier<R, E extends Throwable> {
        R get() throws E;
    }

    static <R, E extends Throwable> R supply(
            ThrowingSupplier<R, E> supplier) throws E {
        return supplier.get();
    }

    public static void main(String[] args) {
        ThrowingSupplier<String, IOException> failingRead = () -> {
            throw new IOException("read failed");
        };

        ThrowingSupplier<String, IOException> successfulRead =
                () -> "data";

        try {
            System.out.println(supply(failingRead));
        } catch (IOException failure) {
            System.out.println("failure=" + failure.getMessage());
        }

        try {
            System.out.println("success=" + supply(successfulRead));
        } catch (IOException failure) {
            System.out.println("unexpected IO");
        }
    }
}
```

```bash
javac GenericLambdaThrowsDemo.java
java GenericLambdaThrowsDemo
```

`stdout`:

```text
failure=read failed
success=data
```

Để đầu ra và suy luận rõ ràng, biến `failingRead` và `successfulRead` được **khai báo kiểu tường minh** `ThrowingSupplier<String, IOException>`.

Giải thích:

- `R` biểu diễn kiểu dữ liệu trả về của lambda (`String`).
- `E` biểu diễn **loại ngoại lệ** lambda được phép truyền ra (`IOException`).
- `ThrowingSupplier.get()` khai báo `throws E` nên thân lambda có thể ném `IOException`.
- `supply` khai báo `throws E` và truyền lỗi ra mà không ép kiểu sang `Exception`.
- Caller biết ngữ cảnh là `IOException` nên có thể viết `catch (IOException)`.
- Ngay cả lambda thành công vẫn có **kiểu interface** cho phép `IOException`, vì thế một lời gọi thông qua kiểu ấy phải đáp ứng hợp đồng checked exception. Compiler không dựa vào việc lambda hiện tại chỉ `return "data"` để bỏ nghĩa vụ.

### Có thể gọi helper với lambda trực tiếp không?

Có thể viết:

```java
String value = GenericLambdaThrowsDemo.supply(() -> "ok");
```

Đây là mảnh minh họa trong ngữ cảnh phù hợp. Với lambda trực tiếp, Java có thể dùng ngữ cảnh đích và các ràng buộc suy luận để chọn type arguments. Khi muốn hợp đồng lỗi dễ đọc và ổn định giữa các lần refactor, **biến typed rõ ràng** hoặc type witness (`ClassName.<R,E>method(...)`) có thể tốt hơn dựa hoàn toàn vào suy luận tinh vi.

Không nên đoán rằng Java sẽ luôn suy ra một kiểu checked exception bạn mong muốn trong mọi biểu thức lambda phức tạp; hãy kiểm tra compiler trên chữ ký thực tế.

## 8. Hàm generic nhận nhiều hành động và giữ cùng loại lỗi

Có thể tái sử dụng một type parameter cho nhiều callback cùng hợp đồng:

```java
@FunctionalInterface
interface Step<E extends Exception> {
    void run() throws E;
}

static <E extends Exception> void runTwo(Step<E> first, Step<E> second)
        throws E {
    first.run();
    second.run();
}
```

Đây là mảnh khai báo hợp lệ. `E extends Exception` phù hợp khi API muốn tập trung vào nhóm exception thay vì `Error`. Nếu hai bước đều có kiểu `Step<IOException>`, caller chỉ phải xử lý `IOException`.

Nhưng hai bước có **hai loại checked exception khác nhánh** có thể khiến việc suy luận một `E` chung phải chọn supertype đủ rộng (chẳng hạn `Exception`) hoặc không phù hợp trong ngữ cảnh cụ thể. Khi API thật sự cần giữ hai loại độc lập, hãy công bố **hai tham số kiểu ngoại lệ**:

```java
static <E1 extends Exception, E2 extends Exception> void runTwoDifferent(
        Step<E1> first, Step<E2> second)
        throws E1, E2 {
    first.run();
    second.run();
}
```

Đây là mảnh phương thức hợp lệ (với `Step` đã định nghĩa). Nó biểu diễn rõ ràng: bước thứ nhất được phép ném `E1`, bước thứ hai được phép ném `E2`. Generic có thể diễn đạt **mối quan hệ** giữa exception ở callback và exception của helper, nhưng bạn phải chọn số tham số kiểu phản ánh đúng hợp đồng.

### Chương trình chạy được: hai loại checked exception độc lập

Tạo tệp **`TwoGenericExceptionsDemo.java`**:

```java
import java.io.IOException;
import java.sql.SQLException;

public class TwoGenericExceptionsDemo {
    @FunctionalInterface
    interface Step<E extends Exception> {
        void run() throws E;
    }

    static <E1 extends Exception, E2 extends Exception> void runBoth(
            Step<E1> first, Step<E2> second) throws E1, E2 {
        first.run();
        second.run();
    }

    public static void main(String[] args) {
        Step<IOException> read = () -> {
            System.out.println("read");
        };

        Step<SQLException> query = () -> {
            throw new SQLException("query failed");
        };

        try {
            runBoth(read, query);
        } catch (IOException failure) {
            System.out.println("IO=" + failure.getMessage());
        } catch (SQLException failure) {
            System.out.println("SQL=" + failure.getMessage());
        }
    }
}
```

```bash
javac TwoGenericExceptionsDemo.java
java TwoGenericExceptionsDemo
```

`stdout`:

```text
read
SQL=query failed
```

`runBoth` không bắt hoặc đổi loại lỗi. Nó truyền `E1` và `E2` ra ngoài. Khi `read` chạy thành công rồi `query` ném `SQLException`, caller nhận đúng loại SQL. Nếu `read` thất bại bằng `IOException`, bước `query` sẽ **không chạy**, trừ khi method được thiết kế bắt/điều phối riêng.

Mẫu này hữu ích khi một thư viện callback có nhiều bước **thật sự cần các loại lỗi riêng**. Không nên gộp thành `throws Exception` nếu generic có thể mô tả hợp đồng chính xác và không làm API khó dùng quá mức.

## 9. Ràng buộc `E extends Throwable` vẫn tuân thủ kiểm tra checked exception

`throws E` không phải quyền miễn trừ kiểm tra compile-time. Nếu caller có type argument cụ thể `IOException`, caller phải xử lý checked exception đó.

Ví dụ:

```java
static <E extends Throwable> void fail(E failure) throws E {
    throw failure;
}

static void caller() {
    fail(new java.io.IOException("disk")); // LỖI: chưa catch/throws.
}
```

Đây là mảnh **cố ý không biên dịch** khi đặt trong một class: `caller()` không bắt hoặc khai báo `IOException`.

Sửa bằng:

```java
static void caller() throws java.io.IOException {
    fail(new java.io.IOException("disk"));
}
```

hoặc:

```java
static void caller() {
    try {
        fail(new java.io.IOException("disk"));
    } catch (java.io.IOException failure) {
        System.out.println(failure.getMessage());
    }
}
```

Hai đoạn sửa là mảnh phương thức hợp lệ nếu đặt cạnh định nghĩa `fail` ở trên.

### Checked exception trong lambda được kiểm tra ở đâu?

Với lambda, compiler kiểm tra thân lambda dựa trên **hàm abstract của functional interface** và phần `throws` tương ứng. Khi interface không công bố checked exception, ném `IOException` là sai. Khi interface công bố `throws E` với kiểu phù hợp, lambda có thể ném `IOException`, còn caller của helper generic phải đáp ứng hợp đồng `throws E` đã suy ra.

Điều này giải thích vì sao chỉ viết:

```java
static <E extends Throwable> void invoke(Runnable task) throws E {
    task.run();
}
```

không làm `Runnable` tự cho phép checked exception trong lambda. `Runnable.run()` vẫn **không khai báo checked exception**. Cách viết generic `throws E` ở **method helper** không sửa chữ ký functional method của `Runnable`. Đây là mảnh method hợp lệ về cú pháp nhưng **không tự tạo khả năng checked exception cho Runnable**.

## 10. Không thể `catch (E e)`: type variable không phải kiểu catch hợp lệ

Đoạn sau **cố ý không biên dịch**:

```java
static <E extends Throwable> void badCatch(E value) {
    try {
        throw value;
    } catch (E failure) { // LỖI: không catch bằng type variable.
        System.out.println(failure.getMessage());
    }
}
```

Java không cho dùng type variable `E` làm kiểu tham số `catch`. Lý do liên quan tới type erasure và quy tắc catch phải dùng kiểu ngoại lệ phù hợp tại runtime; type parameter generic không thể được dùng ở vị trí này như một class exception cụ thể.

**Không nhầm:** `throws E` là hợp lệ; `catch (E e)` là không hợp lệ. `throws` là hợp đồng kiểm tra compile-time, còn `catch` phải có kiểu ngoại lệ cho cơ chế matching tại runtime.

### Cách xử lý hợp lệ

Nếu muốn chuyển tiếp nguyên lỗi, không cần `catch`:

```java
static <E extends Throwable> void passThrough(E error) throws E {
    throw error;
}
```

Nếu cần bắt lỗi chung để thêm ngữ cảnh, có thể bắt một kiểu concrete hợp lệ (`Exception` hoặc `Throwable`) và phải **ném lại/bao bọc phù hợp với checked exception của method**:

```java
static <E extends Throwable> void traceAndPass(
        ThrowingAction<E> action) throws E {
    action.run();
}
```

Đây là mảnh method với `ThrowingAction` từ phần trước, thể hiện cách không cần bắt chỉ để truyền lỗi. Nếu muốn xử lý lỗi theo **một loại cụ thể**, hãy dùng một class exception cụ thể tại ranh giới biết rõ loại đó, ví dụ `catch (IOException e)` khi có đường ném IOException phù hợp.

### `instanceof E` cũng không hợp lệ

`E` không có runtime class token để dùng trực tiếp với `instanceof`:

```java
static <E extends Throwable> boolean isExpected(Throwable failure) {
    return failure instanceof E; // LỖI BIÊN DỊCH.
}
```

Nếu cần kiểm tra runtime type của `E`, API có thể nhận **`Class<E>`**:

```java
static <E extends Throwable> boolean isExpected(
        Throwable failure, Class<E> expected) {
    return expected.isInstance(failure);
}
```

Đây là phương thức hợp lệ. `Class<E>` mang token lớp cụ thể vào runtime, còn type parameter `E` thông thường đã bị xóa kiểu.

## 11. Không thể `new E()`: dùng exception factory

Type parameter generic không thể được khởi tạo trực tiếp:

```java
static <E extends Throwable> E create() {
    return new E(); // LỖI BIÊN DỊCH.
}
```

Lý do không chỉ là “Java không thích generic”. Với `E`, compiler không biết constructor nào có sẵn, và `E` là type variable bị erasure tại runtime. Ngay cả khi biết `E extends Throwable`, không thể suy ra mọi subtype có constructor không tham số hoặc constructor `(String)`.

Nếu API cần **tạo** ngoại lệ theo loại do caller chọn, hãy nhận một factory phù hợp, ví dụ `Function<String,E>`.

### Chương trình chạy được: tạo exception qua factory

Tạo tệp **`GenericExceptionFactoryDemo.java`**:

```java
import java.io.IOException;
import java.util.function.Function;

public class GenericExceptionFactoryDemo {
    static class ValidationException extends Exception {
        ValidationException(String message) {
            super(message);
        }
    }

    static <E extends Exception> void requirePositive(
            int value, Function<String, E> errorFactory) throws E {
        if (value <= 0) {
            throw errorFactory.apply("value must be positive");
        }
    }

    public static void main(String[] args) {
        try {
            requirePositive(0, ValidationException::new);
        } catch (ValidationException failure) {
            System.out.println("validation=" + failure.getMessage());
        }

        try {
            requirePositive(-1, IOException::new);
        } catch (IOException failure) {
            System.out.println("IO=" + failure.getMessage());
        }

        try {
            requirePositive(5, ValidationException::new);
            System.out.println("positive accepted");
        } catch (ValidationException failure) {
            System.out.println("unexpected validation error");
        }
    }
}
```

```bash
javac GenericExceptionFactoryDemo.java
java GenericExceptionFactoryDemo
```

`stdout`:

```text
validation=value must be positive
IO=value must be positive
positive accepted
```

Giải thích:

- `E extends Exception` là loại exception do factory tạo.
- `Function<String,E>` nhận message và tạo một `E` cụ thể; method reference `ValidationException::new` và `IOException::new` cung cấp constructor tương ứng.
- Phương thức generic chỉ biết `E`, nhưng có thể `throw` đối tượng factory trả về nhờ `throws E`.
- Caller bắt loại exception **tương ứng với factory typed**.
- Chọn `IOException` cho lỗi validation chỉ là ví dụ khả năng kiểu, **không phải khuyến nghị thiết kế**: trong ứng dụng nên chọn loại ngoại lệ phản ánh đúng bản chất lỗi.

`Function.apply` bản thân không khai báo checked exception. Nếu **quá trình tạo đối tượng trong factory** cần ném checked exception, phải thiết kế một functional interface có hợp đồng `throws` phù hợp thay vì cho rằng `Function` sẽ tự truyền checked exception.

## 12. Type erasure và giới hạn của generic exception class

Java hỗ trợ **type variable làm kiểu trong `throws`**, nhưng **không** cho khai báo một generic class là subclass của `Throwable`. Ví dụ **cố ý không biên dịch**:

```java
class GenericFailure<T> extends Exception {
    // LỖI: generic class không thể là subclass của Throwable.
}
```

Vì thế không thể thiết kế một ngoại lệ generic mang type parameter như `GenericFailure<String>` rồi bắt bằng `catch (GenericFailure<String> e)`. Đây là giới hạn ngôn ngữ.

Các cấu trúc **hợp lệ** hơn:

```java
class RequestFailure extends Exception {
    RequestFailure(String message) {
        super(message);
    }
}

class ResponseFailure extends Exception {
    ResponseFailure(String message) {
        super(message);
    }
}
```

Hoặc đặt generic ở **method/interface thao tác**, không đặt trên class exception:

```java
interface ThrowingOperation<R, E extends Throwable> {
    R execute() throws E;
}
```

Đây đều là các class/interface minh họa hợp lệ. Exception được biểu diễn bởi các lớp cụ thể, trong khi generic type parameter mô tả **loại lỗi mà một thao tác có thể ném**.

### Vì sao không `E.class`?

`E.class` không hợp lệ vì `E` là type variable, không phải tên class biết tại compile time như `IOException.class`. Nếu cần runtime class, caller truyền `Class<E>`; nếu cần tạo exception, caller truyền factory; nếu cần bọc exception, giữ đối tượng cause thực tế.

## 13. Chuyên biệt hóa generic interface và phương thức override

Generic exception type có thể được đưa vào một interface để lớp triển khai khai báo checked exception phù hợp:

```java
interface Operation<E extends Exception> {
    void run() throws E;
}
```

Khi dùng `Operation<IOException>`, hợp đồng có nghĩa là `run() throws IOException`. Implementation có thể giữ `IOException`, thu hẹp thành subclass (ví dụ `FileNotFoundException`) hoặc không khai báo checked exception. Nó không được tự thêm checked `SQLException` vì không tương thích với `IOException` của interface đã được chuyên biệt hóa.

### Chương trình chạy được: override thu hẹp generic `throws`

Tạo tệp **`GenericOverrideThrowsDemo.java`**:

```java
import java.io.FileNotFoundException;
import java.io.IOException;

public class GenericOverrideThrowsDemo {
    interface Operation<E extends Exception> {
        void run() throws E;
    }

    static class FileOperation implements Operation<IOException> {
        @Override
        public void run() throws FileNotFoundException {
            throw new FileNotFoundException("missing.txt");
        }
    }

    public static void main(String[] args) {
        Operation<IOException> abstractView = new FileOperation();

        try {
            abstractView.run();
        } catch (IOException failure) {
            System.out.println("type="
                    + failure.getClass().getSimpleName());
        }
    }
}
```

```bash
javac GenericOverrideThrowsDemo.java
java GenericOverrideThrowsDemo
```

`stdout`:

```text
type=FileNotFoundException
```

Giải thích:

- `Operation<IOException>` là hợp đồng generic đã có loại lỗi cụ thể.
- `FileOperation.run()` chỉ ném `FileNotFoundException`, subtype của `IOException`, nên override hợp lệ.
- Caller dùng kiểu tĩnh `Operation<IOException>` nên bắt `IOException`.
- Runtime object vẫn là `FileNotFoundException`, được handler `IOException` nhận nhờ quan hệ kế thừa.

**Không nhầm generic throws với việc override được quyền mở rộng checked exception.** Khi interface đã chuyên biệt hóa, các quy tắc checked exception của override vẫn áp dụng.

## 14. Vì sao `Runnable` và `Function` không tự hưởng lợi từ `throws E`?

`java.lang.Runnable.run()` khai báo:

```java
void run();
```

`java.util.function.Function<T,R>.apply(T)` cũng không khai báo checked exception. Do đó, lớp triển khai hoặc lambda gán vào các interface này **không được khai báo checked exception mới** cho functional method.

Không hợp lệ:

```java
Runnable task = () -> {
    throw new java.io.IOException("disk failed");
};
```

Hợp lệ khi **xử lý tại chỗ**:

```java
Runnable task = () -> {
    try {
        operationThatThrowsIOException();
    } catch (java.io.IOException original) {
        throw new IllegalStateException("task failed", original);
    }
};
```

Đây là **mảnh lambda minh họa**, cần định nghĩa `operationThatThrowsIOException()`. Chọn unchecked wrapper có `cause` là quyết định API, không có nghĩa lỗi đã được phục hồi.

Một giải pháp khác là **không dùng `Runnable`/`Function` tại ranh giới cần checked exception**, mà định nghĩa `ThrowingAction<E>` hoặc `ThrowingSupplier<R,E>` với `throws E`.

### Có thể chuyển `ThrowingAction` sang `Runnable` không?

Có thể **adapt** bằng wrapper xử lý hoặc đổi loại exception một cách có ý thức. Nhưng không thể cast tùy tiện một đối tượng implement `ThrowingAction` sang `Runnable` chỉ vì hai interface có method cùng tên `run`; chúng là hai interface độc lập.

Nếu adapter chuyển checked exception thành unchecked, nên giữ nguyên cause và mô tả hợp đồng rõ ràng. Nếu người dùng API phải biết và phục hồi từ checked exception, cần một API callback có khả năng `throws E` ngay từ đầu.

## 15. Kỹ thuật *sneaky throw*: hiểu để tránh lạm dụng

Generic `throws E` có thể bị khai thác để ném một checked exception mà caller **không bị yêu cầu khai báo nó** theo cách thông thường. Đây thường được gọi là *sneaky throw*.

Ví dụ **chạy được nhưng không khuyến nghị dùng để thiết kế API thông thường**:

Tạo file **`SneakyThrowDemo.java`**:

```java
import java.io.IOException;

public class SneakyThrowDemo {
    @SuppressWarnings("unchecked")
    static <E extends Throwable> void sneaky(Throwable failure) throws E {
        throw (E) failure;
    }

    public static void main(String[] args) {
        try {
            SneakyThrowDemo.<RuntimeException>sneaky(
                    new IOException("checked failure"));
        } catch (Throwable failure) {
            System.out.println(
                    failure.getClass().getSimpleName()
                    + ": " + failure.getMessage());
        }
    }
}
```

```bash
javac SneakyThrowDemo.java
java SneakyThrowDemo
```

`stdout`:

```text
IOException: checked failure
```

**Giải thích kỹ thuật:**

1. Phương thức nhận tham số kiểu tĩnh `Throwable`, không phải `E`. Do đó compiler không xác nhận tham số thực sự có kiểu `E`.
2. Ép kiểu `(E) failure` là **unchecked cast**, được gắn `@SuppressWarnings("unchecked")` để tránh cảnh báo; đây không phải bằng chứng về tính an toàn kiểu.
3. Lời gọi chỉ rõ `E = RuntimeException` qua type witness `<RuntimeException>`, khiến hợp đồng `throws E` ở caller trông như unchecked.
4. Runtime vẫn ném **đối tượng IOException thực tế**, không đổi loại nó thành RuntimeException.
5. `catch (Throwable)` chỉ dùng trong ví dụ để in kết quả xác định.

Đừng kết luận rằng checked exception biến thành unchecked thực sự. Nó vẫn là `IOException` ở runtime; chỉ **cơ chế kiểm tra kiểu tại lời gọi** bị làm cho thiếu thông tin chính xác. Điều này có thể phá vỡ kỳ vọng của caller, gây khó bảo trì, làm công cụ phân tích static kém hiệu quả, và tạo ngoại lệ không nằm trong hợp đồng API công khai.

### Tình huống khó xử với `catch (IOException)`

Nếu một lời gọi chỉ được compiler nhìn như ném `RuntimeException`, một handler `catch (IOException)` chỉ dành cho lời gọi đó có thể bị javac từ chối vì **checked IOException không được biết là có thể ném**. Nghĩa là caller mất khả năng xử lý chính loại lỗi mà runtime vẫn có thể tạo ra.

Vì vậy, **không dùng sneaky throw để thay `try/catch`, thay thiết kế functional interface hoặc che lỗi từ caller**. Chỉ nên hiểu cơ chế này khi đọc mã thư viện đặc biệt, nơi tác giả có lý do và hợp đồng rõ ràng.

### Suy luận type parameter trong `throws`

JLS mô tả một số quy tắc đặc biệt khi suy luận type variables có upper bound `Throwable` và chỉ xuất hiện trong ràng buộc `throws`. Trong những tình huống thiếu ràng buộc khác, compiler có thể chọn kiểu unchecked phù hợp (thường `RuntimeException`) làm lựa chọn suy luận. Đây là lý do những API kiểu sneaky throw có thể tồn tại.

Không nên ghi nhớ một mẹo suy luận rồi áp dụng vô điều kiện cho mọi chữ ký generic. Kiểu được suy ra còn phụ thuộc tham số method, kiểu đích, lambda, overload và các ràng buộc khác. Mẫu an toàn hơn là công bố mối quan hệ **thực** giữa callback, loại ngoại lệ và caller, như `ThrowingSupplier<R,E>`.

## 16. Type erasure không xóa đối tượng exception thật

Khi biên dịch generic, nhiều thông tin type parameter không còn hiện diện ở runtime như một kiểu cụ thể độc lập; đây là **type erasure**. Ví dụ upper bound của `E extends Throwable` giúp compiler kiểm tra và xác định cách biểu diễn phù hợp, nhưng `E` không phải một lớp runtime mới.

Do đó:

- Nếu `throw failure;`, đối tượng thực tế vẫn mang class runtime như `IOException` hay `FileNotFoundException`.
- Cơ chế `catch (IOException e)` của mã bên gọi vẫn dựa trên class thực tế của throwable đang truyền.
- `Class<E>` có thể giúp kiểm tra một runtime class cụ thể khi caller cung cấp type token.
- Không dùng `E.class` hoặc `new E()`.
- Không dựa vào cast unchecked để “khẳng định” một đối tượng `Throwable` là subtype `E` do caller chọn.

### Ví dụ runtime type với `Class<E>`

Tạo file **`GenericThrowableClassTokenDemo.java`**:

```java
import java.io.IOException;

public class GenericThrowableClassTokenDemo {
    static <E extends Throwable> boolean matches(
            Throwable value, Class<E> expected) {
        return expected.isInstance(value);
    }

    public static void main(String[] args) {
        Throwable failure = new IOException("disk");

        System.out.println("IOException="
                + matches(failure, IOException.class));
        System.out.println("RuntimeException="
                + matches(failure, RuntimeException.class));
        System.out.println("Throwable="
                + matches(failure, Throwable.class));
    }
}
```

```bash
javac GenericThrowableClassTokenDemo.java
java GenericThrowableClassTokenDemo
```

`stdout`:

```text
IOException=true
RuntimeException=false
Throwable=true
```

`Class.isInstance` thực hiện kiểm tra tương thích runtime. Phương thức generic `matches` không cần ép kiểu và vẫn giữ quan hệ `Class<E>` với type variable. Dùng khi API thật sự cần kiểm tra loại exception do caller chỉ định; nếu chỉ cần chuyển tiếp ngoại lệ, `throws E` và `throw e` đơn giản hơn.

## 17. Precise rethrow và generic `throws E`

Từ Java 7, compiler có phân tích **precise rethrow** cho một số biến exception được bắt và không bị gán lại. Điều này giúp một phương thức bắt một kiểu rộng để quan sát lỗi rồi vẫn khai báo một tập checked exception hẹp tương ứng với các thao tác trong `try`.

Ví dụ:

```java
static <E extends Exception> void executeAndReport(
        ThrowingAction<E> action) throws E {
    try {
        action.run();
    } catch (Exception failure) {
        System.out.println("action failed: " + failure.getMessage());
        throw failure;
    }
}
```

Đây là **mảnh phương thức minh họa** với interface `ThrowingAction<E>` đã được định nghĩa ở trên. Vì tham số `failure` của `catch` không bị gán lại và phần thân `try` chỉ chuyển tiếp ngoại lệ từ `action.run()`, Java có thể áp dụng phân tích rethrow chính xác trong phạm vi các ràng buộc checked exception của `E`.

Tuy nhiên, cần phân biệt hai cơ chế:

1. **Generic `throws E`**: mối liên hệ tĩnh giữa loại lỗi của callback và loại lỗi của helper.
2. **Precise rethrow**: phân tích compiler về checked exception thực sự có thể ném từ khối `try` và tính effectively final của biến được bắt.

Không phải hễ viết `catch (Exception)` hoặc `catch (Throwable)` là có thể `throw` lại mà không khai báo; phụ thuộc chữ ký, các lời gọi trong `try` và quy tắc kiểm tra ngoại lệ.

Nếu không cần thêm log/ngữ cảnh, **đừng bắt chỉ để ném lại**: đơn giản viết `action.run();` cho rõ hợp đồng và tránh log lặp.

### `throws E` không bảo đảm giữ nguyên stack trace nếu bạn bọc sai

`throw original;` truyền cùng đối tượng throwable, còn:

```java
throw new IllegalStateException("failed", original);
```

tạo một đối tượng mới và giữ `original` làm `cause`. Cả hai là cách đúng tùy ranh giới API, nhưng có **ý nghĩa khác nhau**. Không chỉ copy `original.getMessage()` vì có thể mất stack trace/cause/suppressed của lỗi gốc.

## 18. Những lỗi compile-time thường gặp

| Mã / tình huống | Hợp lệ? | Lý do |
| --- | --- | --- |
| `<E extends Throwable> void run(E e) throws E { throw e; }` | Có | E là throwable và được khai báo trong throws |
| `<E extends Throwable> void run(E e) { throw e; }` | **Không**, nói chung | Có thể truyền checked E nhưng thiếu catch/throws |
| `<E extends RuntimeException> void run(E e) { throw e; }` | Có | E bị giới hạn vào nhánh unchecked |
| `catch (E e)` khi E là type variable | **Không** | Type variable không là kiểu catch hợp lệ |
| `new E()` | **Không** | Không thể tạo instance trực tiếp từ type parameter |
| `value instanceof E` | **Không** | Type variable không là runtime reifiable type |
| `E.class` | **Không** | Không tồn tại class literal cho type variable |
| `class Failure<E> extends Exception` | **Không** | Generic class không được là subclass của Throwable |
| `class Failure extends Exception` | Có | Exception class không generic |
| `ThrowingAction<IOException> action = () -> { throw new IOException(); };` | Có | Functional method khai báo throws E = IOException |
| `Runnable action = () -> { throw new IOException(); };` | **Không** | Runnable.run() không công bố checked exception |
| `static <E extends Throwable> void run(ThrowingAction<E> a) throws E` | Có với method body phù hợp | Generic callback bảo toàn hợp đồng lỗi |
| `Operation<IOException>` được implement với `throws FileNotFoundException` | Có | Override thu hẹp checked type |
| `Operation<IOException>` được implement với `throws SQLException` | **Không** | Override thêm checked exception khác nhánh |
| `<RuntimeException>sneaky(new IOException())` | Có thể qua unchecked cast | Kỹ thuật che hợp đồng, không khuyến nghị |

Các dòng là **mảnh cú pháp rút gọn**, không phải toàn bộ chương trình. Bảng xét ý nghĩa generic/exception chính; class, interface, phương thức và quyền truy cập vẫn phải được khai báo phù hợp.

## 19. Thiết kế API: chọn `E extends Throwable` hay `E extends Exception`?

Khi thiết kế library, nên chọn bound đủ hẹp theo nhu cầu.

### `E extends Throwable`

Phù hợp nếu muốn mô hình hóa callback/operation có thể truyền **mọi subtype Throwable**, bao gồm `Error`. Nhưng đây là phạm vi rất rộng. Đừng chọn chỉ vì “trông tổng quát” nếu callers và chính sách xử lý của ứng dụng không có lý do công bố `Error` trong hợp đồng kiểu.

### `E extends Exception`

Phù hợp nếu API liên quan chủ yếu tới nhóm exception của ứng dụng và checked exception của business/I/O. Nó vẫn nhận `RuntimeException`, nhưng không nhận `Error` qua type argument `E`. Unchecked `Error` vẫn có thể phát sinh thực tế; bound này không phải cơ chế ngăn JVM ném Error.

### `E extends IOException` hoặc một ngoại lệ miền cụ thể

Hữu ích khi helper chỉ phục vụ một họ lỗi và caller cần biết giới hạn rõ ràng. Chọn bound rộng hơn `IOException` nếu API thật sự phải xử lý các loại checked exception khác nhánh.

### Khi nào **không cần generic exception type**?

Nếu API chỉ gọi một thao tác cố định luôn công bố `IOException`, một chữ ký thường:

```java
static String read() throws java.io.IOException {
    return "data";
}
```

có thể dễ hiểu hơn tạo `<E extends Throwable>` giả. Generic exception type có giá trị khi tồn tại **mối liên hệ thực giữa type argument của caller/callback và lỗi được truyền**, không phải khi method chỉ muốn né một loại checked exception cụ thể.

### Không lạm dụng nhiều type parameter

Một API với `<R,T,E1,E2,E3>` có thể rất khó đọc. Dùng khi hợp đồng nhiều loại lỗi thực sự cần phân biệt; nếu độ phức tạp vượt lợi ích, cân nhắc một loại domain exception có cause đúng hoặc thiết kế operation/result object. Không dùng `throws Exception` chỉ để bỏ qua thiết kế lỗi, nhưng cũng không ép mọi helper đơn giản thành khung generic phức tạp.

## 20. Những nhầm lẫn phổ biến

**“`E extends Throwable` nghĩa là mọi `E` đều checked exception.”** Sai. `RuntimeException` và `Error` là unchecked.

**“`throws E` nghĩa là luôn phải bắt `Throwable` ở caller.”** Sai. Nếu `E` được suy ra/chỉ định là `IOException`, caller chỉ cần hợp đồng checked tương ứng.

**“Có generic `throws E` thì lambda gán vào `Runnable` được phép ném IOException.”** Sai. Lambda phải tuân thủ `throws` của phương thức abstract trong functional interface đích.

**“`<E extends Throwable>` là một kiểu ngoại lệ mới ở runtime.”** Sai. Đó là type parameter với upper bound, chịu type erasure.

**“Có thể `catch (E failure)` vì E extends Throwable.”** Sai. Java cấm type variable làm kiểu catch.

**“Có thể tạo ngoại lệ với `new E()`.”** Sai. Truyền factory hoặc class token cùng cơ chế tạo có kiểm soát.

**“Hai class exception đều có constructor (String) nên compiler tự biết tạo E.”** Sai. Constructor không được suy ra theo mọi subtype của bound; cần factory cụ thể.

**“Generic exception class `MyException<T> extends Exception` là bình thường.”** Sai. Java cấm generic subclass của `Throwable`.

**“`ThrowingSupplier<R,E>` thay thế hoàn toàn `Function<T,R>` mà không có gì đổi.”** Không. Chúng có hợp đồng functional method khác nhau, không thay thế/cast trực tiếp tùy tiện.

**“`throws E` cho phép method override thêm mọi checked exception.”** Sai. Sau khi type argument được chuyên biệt hóa, quy tắc override checked exception vẫn áp dụng.

**“Sneaky throw đã chuyển IOException thành RuntimeException.”** Sai. Runtime object vẫn là IOException; kỹ thuật chỉ làm caller không thấy đúng checked contract.

**“`@SuppressWarnings("unchecked")` khiến cast an toàn về kiểu.”** Sai. Nó chỉ ẩn cảnh báo, không chứng minh tương thích runtime.

**“Nếu lambda hiện tại không ném lỗi, caller có thể bỏ checked handler dù interface ghi throws E.”** Sai. Kiểm tra dựa trên chữ ký functional interface/type tại lời gọi.

**“`getClass()` hoặc `Class<E>` là lúc nào cũng cần để generic rethrow.”** Không. Truyền `E e` và `throw e` là đủ nếu chỉ chuyển tiếp loại lỗi.

**“Có thể bỏ `throws E` khi throw E vì compiler nhìn bound Throwable.”** Sai trong trường hợp E có thể checked. Bound chứng minh throwable, không tự khai báo lỗi.

**“Bắt rồi ném lại luôn cần tạo một exception mới để giữ stack trace.”** Sai. `throw original;` bảo toàn đối tượng cũ; bọc bằng cause là việc khác.

## 21. Bài tập tự kiểm tra

### Bài 1: Generic bound

```java
static <E extends Throwable> void fail(E e) throws E {
    throw e;
}
```

**Hỏi:** `E` có thể là `IOException`, `IllegalArgumentException`, `AssertionError` không? **Đáp:** Cả ba đều được về bound; quy tắc checked/unchecked khi gọi phụ thuộc kiểu cụ thể.

### Bài 2: Bỏ `throws E`

```java
static <E extends Throwable> void fail(E e) {
    throw e;
}
```

**Hỏi:** Có biên dịch không? **Đáp:** Không trong dạng này, vì `E` có thể là checked exception và method không bắt/khai báo.

### Bài 3: Lambda

```java
@FunctionalInterface
interface Action<E extends Exception> {
    void run() throws E;
}
```

**Hỏi:** `Action<IOException>` có thể dùng lambda ném `IOException` không? **Đáp:** Có, nếu IOException được khai báo hoặc ghi tên đầy đủ và lambda theo hợp đồng interface.

### Bài 4: Catch type variable

```java
static <E extends Exception> void use(E e) {
    try {
        throw e;
    } catch (E caught) {
    }
}
```

**Hỏi:** Cách catch có hợp lệ không? **Đáp:** Không; type variable `E` không được dùng làm kiểu của tham số `catch`.

### Bài 5: Class exception generic

```java
class ValidationFailure<T> extends Exception {
}
```

**Hỏi:** Có biên dịch không? **Đáp:** Không. Generic class không thể là subclass của `Throwable`.

### Bài 6: Runtime type

```java
static <E extends Throwable> boolean test(
        Throwable e, Class<E> expected) {
    return expected.isInstance(e);
}
```

**Hỏi:** Phương thức này có cần `E.class` không? **Đáp:** Không. Caller cung cấp token `Class<E>`.

### Bài 7: Rethrow qua generic

Nếu `ThrowingSupplier<String, IOException> s` ném `IOException`, `supply(s) throws E` với `E=IOException` có cần caller bắt/khai báo IOException không? **Có.**

### Bài 8: Hai loại lỗi

Nếu callback A có `Step<IOException>`, callback B có `Step<SQLException>`, có thể dùng method `<E1 extends Exception,E2 extends Exception> runBoth(...) throws E1,E2` không? **Có.** Caller cần xử lý cả hai checked type nếu chúng có thể thoát.

### Bài 9: Sneaky throw

Một method khai báo generic `throws E` nhưng nội bộ cast unchecked từ `Throwable` sang `E`, caller chỉ định `E=RuntimeException` rồi truyền `IOException`. **Runtime exception object là gì?** Vẫn là `IOException`. Đây là lý do không nên dùng để giấu checked exception.

### Bài 10: Override

`interface Op<E extends Exception> { void run() throws E; }`. Class implements `Op<IOException>` có thể override `run() throws FileNotFoundException` không? **Có**, vì subtype checked được cho phép.

### Bài 11: Factory

Tại sao `<E extends Exception> E make() { return new E(); }` sai, còn nhận `Function<String,E> factory` rồi `factory.apply(message)` có thể đúng? Vì generic không biết constructor thật của `E`, còn factory do caller cung cấp thao tác tạo cụ thể.

### Bài 12: Bound `Exception`

`E extends Exception` có chấp nhận `IllegalStateException` không? **Có** vì là subclass của `RuntimeException`, mà `RuntimeException` kế thừa `Exception`. Nó có chấp nhận `AssertionError` làm type argument không? **Không**, vì `Error` không kế thừa `Exception`.

## 22. Tài liệu Java 17

- [Java Language Specification 17 — 8.4.6 Method Throws](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.6): cho phép type variables phù hợp trong `throws`.
- [Java Language Specification 17 — 11.2 Compile-Time Checking of Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.2): loại checked exception và nghĩa vụ catch/throws.
- [Java Language Specification 17 — 18.4 Resolution](https://docs.oracle.com/javase/specs/jls/se17/html/jls-18.html#jls-18.4): suy luận type variables, bao gồm những ràng buộc liên quan `throws`.
- [Java Language Specification 17 — 15.27 Lambda Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.27): kiểm tra checked exception từ thân lambda theo functional interface.
- [Java Language Specification 17 — 14.20 try/catch](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20): kiểu bắt ngoại lệ và quy tắc lựa chọn handler.
- [Java Language Specification 17 — 8.1.2 Generic Classes and Type Parameters](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.2): generic class không được là subclass của Throwable.
- [Java Language Specification 17 — 8.4.8.3 Override Throws](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.8.3): giới hạn checked exception khi ghi đè phương thức.
- [Java SE 17 API — Throwable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): lớp gốc của cơ chế exception.
- [Java SE 17 API — Runnable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runnable.html) và [Function](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/Function.html): functional methods không khai báo checked exception.
- [Java SE 17 API — Class.isInstance](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#isInstance(java.lang.Object)): kiểm tra runtime type bằng class token.

**Ghi nhớ:** `<E extends Throwable>` cho phép phương thức generic mô tả **loại ngoại lệ E** trong tham số, callback và `throws E`, nhờ đó có thể chuyển tiếp checked exception với hợp đồng rõ ràng. Nhưng type variable không thay thế một class exception cụ thể ở runtime: không `catch (E)`, không `new E()`, không `E.class`. Hãy sử dụng generic `throws` để **giữ thông tin kiểu thật của callback/caller**, không dùng unchecked cast hay *sneaky throw* để che giấu checked exception khỏi người sử dụng API.
