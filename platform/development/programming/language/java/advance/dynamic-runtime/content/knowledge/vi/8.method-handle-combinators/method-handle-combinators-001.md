# 8.1 Tạo handle nền bằng constant, identity, empty và throwException

## 1. Tại sao cần các handle nền?

Trong Java, `MethodHandle` là đối tượng biểu diễn một phép tính có chữ ký kiểu cụ thể, chứ không nhất thiết luôn trỏ đến một method đã được khai báo trong class. Bên cạnh `Lookup.findStatic`, `findVirtual` và các phép tìm member, lớp `java.lang.invoke.MethodHandles` có các factory tạo ra những thao tác cơ bản để ghép thành luồng gọi động.

Bốn factory của bài học đều **tạo handle trực tiếp, không cần `MethodHandles.Lookup`**:

| Factory | Chữ ký handle được tạo | Hành vi khi gọi |
| --- | --- | --- |
| `constant(T.class, value)` | `()T` | Trả cùng giá trị đã gắn khi tạo handle. |
| `identity(T.class)` | `(T)T` | Trả nguyên tham số nhận được. |
| `empty(MethodType.methodType(R.class, A...))` | `(A...)R` | Bỏ qua đối số, trả giá trị mặc định theo `R`; nếu `R=void` thì không làm gì. |
| `throwException(R.class, E.class)` | `(E)R` | Ném đối tượng ngoại lệ kiểu `E` được truyền vào; không trả bình thường. |

Ở đây `T` là kiểu **khác void**; `R` có thể là kiểu giá trị hoặc `void`; `E` là lớp con của `Throwable`. Những handle này thường làm hạt nhân cho nhánh hằng số, đường dữ liệu đi thẳng, no-op, và nhánh lỗi của một combinator graph.

### 1.1. Mục tiêu học tập

Sau bài này bạn sẽ biết cách:

1. Dự đoán chính xác `MethodType` và giá trị của từng factory.
2. Hiểu chuyển kiểu lúc tạo `constant`, giá trị mặc định của `empty` và kiểu trả về danh nghĩa của `throwException`.
3. Gọi bằng `invokeExact` với kiểu đầu vào/đầu ra phù hợp, tránh `WrongMethodTypeException`.
4. Kết hợp `dropArguments`, `insertArguments` và `guardWithTest` để tạo một luồng gọi động từ các handle nền.
5. Nhận biết lỗi dùng `void`, `null`, object mutable và exception được tái sử dụng.

## 2. Nền tảng: phân biệt factory, chữ ký và lời gọi

Mỗi handle có phương thức `type()` trả về `MethodType`, tức danh sách **kiểu tham số theo thứ tự** và **kiểu trả về**. Một số dạng:

```text
()String                     không có đầu vào, trả String
(String)String               nhận String, trả String
(String,long)int             nhận String và long, trả int
(IllegalArgumentException)int nhận exception, có return type danh nghĩa int
```

`MethodType.methodType(int.class, String.class, long.class)` biểu diễn chữ ký `(String,long)int`. Đây là **kiểu của handle**, không phải cú pháp khai báo Java method thông thường.

`invokeExact(...)` là lời gọi signature-polymorphic yêu cầu chữ ký tại call site **khớp chính xác** handle: cùng số tham số, cùng kiểu tham số, cùng kiểu trả về. Ví dụ `()int` chỉ khớp với ngữ cảnh nhận `int` và **0 đối số**; không thể truyền một đối số tùy tiện cho nó.

Vì thế:

```java
MethodHandle h = MethodHandles.constant(int.class, 5);
int number = (int) h.invokeExact();  // đúng: ()int
// int wrong = (int) h.invokeExact(9);  // sai: call site (int)int
```

Đoạn mã minh họa bên trong một phương thức đã import `MethodHandle`/`MethodHandles` và xử lý `Throwable`. Nếu bỏ comment ở dòng cuối và chạy, lời gọi sai thường ném `WrongMethodTypeException`.

Trong ví dụ đầy đủ, `main` khai báo `throws Throwable` vì `invokeExact` có thể ném `Throwable`. Code ứng dụng nên có ranh giới xử lý lỗi rõ ràng, không nuốt mọi ngoại lệ.

## 3. `MethodHandles.constant(type, value)` — handle hằng số

Ví dụ:

```java
MethodHandle ready = MethodHandles.constant(String.class, "READY");
// ready.type() là ()String
String text = (String) ready.invokeExact();  // READY
```

**Đặc điểm:**

- Handle được tạo có **0 tham số** và kiểu trả về `type`. Mọi lời gọi bình thường trả cùng giá trị đã chọn.
- Giá trị được chuyển sang kiểu `type` **ngay khi tạo handle**. Với primitive, Java thực hiện unbox và thử widening primitive conversion phù hợp: `constant(long.class, Integer.valueOf(7))` hợp lệ, trả `7L`.
- Với kiểu tham chiếu, giá trị phải tương thích kiểu yêu cầu; `constant(CharSequence.class, "hi")` hợp lệ, còn `constant(String.class, new StringBuilder("hi"))` không chuyển `StringBuilder` thành `String`.
- `constant(String.class, null)` hợp lệ và trả `null`. Không dùng `constant` để parse một chuỗi thành số.
- `constant(void.class, value)` ném `IllegalArgumentException`; `type == null` ném `NullPointerException`; giá trị không thể chuyển sang kiểu cần thiết có thể ném `ClassCastException`.

### 3.1. Hằng số tham chiếu không có nghĩa là object bất biến

Một `StringBuilder` được bind vào `constant(StringBuilder.class, builder)` **không được clone**. Handle trả lại cùng tham chiếu. Nếu code khác thay đổi `builder`, lần gọi handle sau có thể quan sát nội dung mới. Vì thế, nếu muốn một cấu hình bất biến, nên bind dữ liệu immutable (ví dụ `String`) hoặc tự sao chép trước khi bind. `constant` không thay thế cơ chế đồng bộ hóa object mutable giữa các thread.

### 3.2. Muốn nhận thêm tham số thì dùng adapter

Handle `()String` không tự nhận thêm argument. Để bỏ qua một `long id` nhưng vẫn luôn trả `"OK"`:

```java
MethodHandle base = MethodHandles.constant(String.class, "OK");
MethodHandle withId = MethodHandles.dropArguments(
        base, 0, long.class);
// withId.type(): (long)String
```

Đây là đoạn minh họa, không phải file độc lập. `dropArguments` **chèn các tham số giả** vào chữ ký của handle; chúng được caller cung cấp nhưng không ảnh hưởng kết quả của `base`.

## 4. `MethodHandles.identity(type)` — nhận và trả chính input

`identity(T.class)` tạo một handle `(T)T`: đúng một tham số và một giá trị trả về cùng kiểu. Không có tham số `value` khi tạo; giá trị được cung cấp khi **invoke**.

```java
MethodHandle textId = MethodHandles.identity(String.class);
MethodHandle intId = MethodHandles.identity(int.class);
// textId.type() là (String)String
// intId.type() là (int)int
String text = (String) textId.invokeExact("hello");
int number = (int) intId.invokeExact(42);
```

Cả hai lời gọi trả lại đúng giá trị đầu vào. Với kiểu reference, `identity` trả **chính object**, không copy hoặc clone; input `null` được trả lại thành `null`. Với primitive, nó trả đúng giá trị primitive cùng kiểu.

**Không thể dùng `identity(void.class)`** vì `void` không phải kiểu tham số Java, factory ném `IllegalArgumentException`. Nếu `type == null`, factory ném `NullPointerException`.

### 4.1. Khi nào nên dùng?

- Bước transform tùy chọn không được cấu hình: dùng identity làm đường **pass-through**.
- Nhánh không cần thay đổi dữ liệu nhưng phải có handle đúng signature `(T)T`.
- Predicate cho điều kiện boolean: `identity(boolean.class)` có dạng `(boolean)boolean`, trả nguyên điều kiện (sử dụng ở mục 8).

Đừng nhầm `identity` với `constant`. `constant(String.class, "X")` không nhận input; `identity(String.class)` bắt buộc nhận input String khi gọi. Nó cũng khác về API với `Function.identity()` của Java generics: hai thứ đều trả đầu vào, nhưng một bên là `MethodHandle` có kiểu runtime, một bên là `java.util.function.Function`.

## 5. `MethodHandles.empty(methodType)` — không làm gì, vẫn đúng chữ ký

`empty(MethodType type)` tạo handle **có đúng chữ ký đã chỉ định**. Khi được gọi, handle **bỏ qua giá trị các tham số**, không thực hiện thao tác tùy chỉnh và trả giá trị mặc định dựa vào kiểu trả về:

| Kiểu trả về | Kết quả của empty |
| --- | --- |
| `byte`, `short`, `int`, `long` | `0` đúng kiểu |
| `float`, `double` | `0.0f` hoặc `0.0d` |
| `boolean` | `false` |
| `char` | Ký tự NUL, mã số 0 |
| Reference type như `String`, `Object`, array | `null` |
| `void` | Hoàn thành bình thường, không có kết quả |

Ví dụ:

```java
MethodHandle zeroInt = MethodHandles.empty(
        MethodType.methodType(int.class, String.class, long.class));
// zeroInt.type() là (String,long)int

MethodHandle noText = MethodHandles.empty(
        MethodType.methodType(String.class, int.class));
// noText.type() là (int)String

MethodHandle noOp = MethodHandles.empty(
        MethodType.methodType(void.class, String.class));
// noOp.type() là (String)void
```

Khi gọi `zeroInt` bằng `"unused"` và `99L`, kết quả luôn là `0`; `noText` trả `null`; `noOp` không làm gì.

**Lưu ý cực quan trọng:** Java vẫn **đánh giá các biểu thức đối số ở phía caller** trước khi gọi handle. Nếu đối số là `sideEffect()`, side effect đó có thể xảy ra dù `empty` không dùng giá trị. Chỉ nội bộ handle rỗng mới không làm gì.

### 5.1. Quan hệ với `MethodHandles.zero`

`MethodHandles.zero(T.class)` (Java 9+) tạo handle `()T` trả **giá trị mặc định** của `T`. Theo Javadoc Java 17, nó tương đương `empty(MethodType.methodType(T.class))`. Tổng quát, `empty(type)` có thể xem như `zero(type.returnType())` rồi thêm các tham số bị bỏ qua bằng `dropArguments`.

Khác biệt dễ quên:

- `zero(void.class)` và `empty(methodType(void.class))` **hợp lệ**.
- `constant(void.class, ...)` **không hợp lệ**, vì `constant` cần một giá trị để trả về.
- `zero(int.class)` và `constant(int.class, 0)` có kết quả giống nhau, nhưng một factory tạo **giá trị mặc định** còn một factory nhận **giá trị do caller chọn**.

### 5.2. Cẩn thận khi chọn no-op

`empty` là giải pháp tốt cho nhánh tùy chọn **được phép không xử lý**. Nhưng nó không phù hợp nếu thiếu handler phải được coi là lỗi. Trong pipeline, một kết quả `0`, `false` hoặc `null` có thể bị hiểu nhầm là thành công. Khi trạng thái không hợp lệ, nhánh `throwException` có thể phù hợp hơn.

## 6. `MethodHandles.throwException(returnType, exType)` — nhánh luôn ném

`throwException(R.class, E.class)` tạo handle dạng **`(E)R`**, trong đó `E extends Throwable`. Nó **nhận một đối tượng exception** rồi **ném chính đối tượng đó** khi được gọi; không tự tạo exception.

```java
MethodHandle fail = MethodHandles.throwException(
        String.class, IllegalArgumentException.class);
// fail.type(): (IllegalArgumentException)String
```

`String` là **kiểu trả về danh nghĩa**; handle không bao giờ có đường trả về bình thường, dù kiểu này là `String`, `int` hay `void`. Chữ ký trả về danh nghĩa giúp nó có thể tham gia graph với một nhánh trả đúng kiểu `R`.

**Khác nhau giữa tạo và gọi:**

- Gọi factory `throwException(...)` tạo handle, không ném ngoại lệ nghiệp vụ.
- Gọi `fail.invokeExact(problem)` ném **problem**, nếu call site có đúng chữ ký `(IllegalArgumentException)String`.
- Vì tham số thật là exception object, bạn kiểm soát loại, thông điệp và stack trace bằng cách tạo exception trước khi invoke.
- `returnType` / `exType` không được `null`; kiểu `exType` phải là con `Throwable`.

### 6.1. Checked exception vẫn hoạt động

`throwException(void.class, IOException.class)` tạo handle `(IOException)void`. Khi gọi bằng một `IOException`, nó ném checked exception ấy. Kiểu `void` không làm mất ngoại lệ; nó chỉ mô tả kiểu trả về mà handle sẽ **không bao giờ đạt đến**.

### 6.2. Ghép nhánh throw bằng `insertArguments`

Nếu một nhánh `(boolean)String` cần ném `IllegalStateException("disabled")` mà không muốn nhận exception ở lời gọi cuối, dùng:

1. `throwException(String.class, IllegalStateException.class)` tạo `(IllegalStateException)String`.
2. `insertArguments(thrower, 0, exception)` bind exception, tạo `()String`.
3. `dropArguments(bound, 0, boolean.class)` tạo `(boolean)String`, sẵn sàng ghép với nhánh khác.

Không nên bind một exception mutable/có stack trace nhạy cảm rồi tái sử dụng ở mọi yêu cầu nếu cần thông tin lỗi riêng từng lần. Khi exception được bind sẵn, mỗi lần gọi có thể ném lại **cùng object**, không phải exception mới với stack trace của từng request.

Nếu truyền `null` như tham số exception tại lần invoke, phép ném null sinh `NullPointerException`. Đây không phải cơ chế báo lỗi nên dùng có chủ đích.

## 7. Ví dụ Java 17 chạy được: bốn factory trong một chương trình

Tạo file **`BaseHandlesDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class BaseHandlesDemo {
    public static void main(String[] args) throws Throwable {
        MethodHandle fixed =
                MethodHandles.constant(String.class, "READY");
        MethodHandle wide =
                MethodHandles.constant(long.class, Integer.valueOf(7));
        MethodHandle textId = MethodHandles.identity(String.class);
        MethodHandle intId = MethodHandles.identity(int.class);
        MethodHandle ignored = MethodHandles.empty(
                MethodType.methodType(int.class, String.class, long.class));
        MethodHandle noText = MethodHandles.empty(
                MethodType.methodType(String.class, int.class));
        MethodHandle noOp = MethodHandles.empty(
                MethodType.methodType(void.class, String.class));
        MethodHandle fail = MethodHandles.throwException(
                String.class, IllegalArgumentException.class);

        System.out.println("constant type: " + fixed.type());
        System.out.println("constant: " + (String) fixed.invokeExact());
        System.out.println("widened: " + (long) wide.invokeExact());
        System.out.println("identity type: " + textId.type());
        System.out.println("identity text: "
                + (String) textId.invokeExact("hello"));
        System.out.println("identity int: " + (int) intId.invokeExact(42));
        System.out.println("empty type: " + ignored.type());
        System.out.println("empty int: "
                + (int) ignored.invokeExact("unused", 99L));
        System.out.println("empty reference null: "
                + ((String) noText.invokeExact(123) == null));

        noOp.invokeExact("discarded");
        System.out.println("empty void: returned normally");

        System.out.println("throw type: " + fail.type());
        IllegalArgumentException problem =
                new IllegalArgumentException("invalid");
        try {
            String result = (String) fail.invokeExact(problem);
            System.out.println("unreachable: " + result);
        } catch (IllegalArgumentException ex) {
            System.out.println("same exception object: " + (ex == problem));
            System.out.println("exception message: " + ex.getMessage());
        }
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 --release 17 BaseHandlesDemo.java
java BaseHandlesDemo
```

Stdout:

```text
constant type: ()String
constant: READY
widened: 7
identity type: (String)String
identity text: hello
identity int: 42
empty type: (String,long)int
empty int: 0
empty reference null: true
empty void: returned normally
throw type: (IllegalArgumentException)String
same exception object: true
exception message: invalid
```

**Giải thích kết quả:**

- `fixed` không nhận input; `wide` chứng minh chuyển wrapper `Integer` sang primitive `long` khi tạo constant.
- `textId` có `(String)String`; `intId` trả nguyên primitive `int`.
- `ignored` nhận hai giá trị đúng kiểu `String` và `long` nhưng không sử dụng chúng, trả `0`.
- `noText` trả `null` cho kiểu tham chiếu `String`; `noOp` có kiểu `(String)void`.
- `fail` được tạo bình thường; **chỉ lần gọi** mới ném `IllegalArgumentException`. Biểu thức `ex == problem` là `true` vì đó là đúng instance đã được đưa vào.

Lệnh `javac --release 17` làm ví dụ sử dụng API tương thích Java 17; `MethodHandles.empty` và `zero` đã có từ Java 9. Cần chạy với runtime hỗ trợ ít nhất các API được sử dụng.

## 8. Ví dụ Java 17: kết hợp thành nhánh động bằng `guardWithTest`

Dùng `identity(boolean.class)` làm điều kiện, `constant` làm các giá trị nhánh. Vì constant có kiểu `()String` nhưng graph nhận `boolean`, phải thêm tham số giả bằng `dropArguments`.

Tạo file **`BaseCompositionDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;

public class BaseCompositionDemo {
    public static void main(String[] args) throws Throwable {
        MethodHandle test = MethodHandles.identity(boolean.class);
        MethodHandle yes = MethodHandles.dropArguments(
                MethodHandles.constant(String.class, "ACCEPT"),
                0, boolean.class);
        MethodHandle no = MethodHandles.dropArguments(
                MethodHandles.constant(String.class, "REJECT"),
                0, boolean.class);
        MethodHandle choose = MethodHandles.guardWithTest(test, yes, no);

        System.out.println("choose type: " + choose.type());
        System.out.println("choose true: "
                + (String) choose.invokeExact(true));
        System.out.println("choose false: "
                + (String) choose.invokeExact(false));

        MethodHandle throwOne = MethodHandles.insertArguments(
                MethodHandles.throwException(
                        String.class, IllegalStateException.class),
                0, new IllegalStateException("disabled"));
        MethodHandle bad = MethodHandles.dropArguments(
                throwOne, 0, boolean.class);
        MethodHandle enforce =
                MethodHandles.guardWithTest(test, yes, bad);

        System.out.println("enforce true: "
                + (String) enforce.invokeExact(true));
        try {
            String value = (String) enforce.invokeExact(false);
            System.out.println("unreachable: " + value);
        } catch (IllegalStateException ex) {
            System.out.println("enforce false: " + ex.getMessage());
        }
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 --release 17 BaseCompositionDemo.java
java BaseCompositionDemo
```

Stdout:

```text
choose type: (boolean)String
choose true: ACCEPT
choose false: REJECT
enforce true: ACCEPT
enforce false: disabled
```

### 8.1. Quan sát thay đổi kiểu của handle

```text
identity(boolean.class)                    : (boolean)boolean
constant(String.class,"ACCEPT")             : ()String
  + dropArguments(..., boolean.class)      : (boolean)String
constant(String.class,"REJECT")             : ()String
  + dropArguments(..., boolean.class)      : (boolean)String
guardWithTest(test, yes, no)               : (boolean)String

throwException(String, IllegalStateException): (IllegalStateException)String
  + insertArguments(..., exception)        : ()String
  + dropArguments(..., boolean.class)      : (boolean)String
guardWithTest(test, yes, bad)              : (boolean)String
```

- `test` nhận `boolean` và trả `boolean`.
- `yes` và `no` cùng có signature `(boolean)String`, vì vậy ghép được bằng `guardWithTest`.
- `throwOne` giữ một `IllegalStateException` đã bind; `bad` có kiểu `(boolean)String` nhưng không bao giờ trả `String` khi bị chọn.
- Trong `enforce`, `true` trả `ACCEPT`, `false` ném exception với thông điệp `disabled`.

Đây là ví dụ về **lắp ghép luồng gọi khi runtime**. Với `if/else` tĩnh trong Java thông thường, hãy ưu tiên code đơn giản nếu không có nhu cầu sinh/đổi graph lúc chạy.

## 9. Ví dụ Java 17: kiểm tra ranh giới kiểu và tính bất biến

Tạo file **`BaseHandleEdgesDemo.java`**:

```java
import java.io.IOException;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;

public class BaseHandleEdgesDemo {
    public static void main(String[] args) throws Throwable {
        MethodHandle zero = MethodHandles.zero(int.class);
        MethodHandle empty = MethodHandles.empty(
                MethodType.methodType(int.class));
        System.out.println("zero and empty: "
                + ((int) zero.invokeExact() == (int) empty.invokeExact()));

        MethodHandle typedNull =
                MethodHandles.constant(String.class, null);
        System.out.println("typed null: "
                + ((String) typedNull.invokeExact() == null));

        StringBuilder buffer = new StringBuilder("A");
        MethodHandle captured =
                MethodHandles.constant(StringBuilder.class, buffer);
        buffer.append("B");
        System.out.println("same mutable object: "
                + (((StringBuilder) captured.invokeExact()) == buffer));
        System.out.println("current contents: "
                + ((StringBuilder) captured.invokeExact()).toString());

        try {
            MethodHandles.identity(void.class);
        } catch (IllegalArgumentException ex) {
            System.out.println("identity void: rejected");
        }
        try {
            MethodHandles.constant(void.class, "ignored");
        } catch (IllegalArgumentException ex) {
            System.out.println("constant void: rejected");
        }

        MethodHandle fixed = MethodHandles.constant(int.class, 5);
        try {
            int value = (int) fixed.invokeExact(9);
            System.out.println(value);
        } catch (WrongMethodTypeException ex) {
            System.out.println("invokeExact signature: rejected");
        }

        IOException problem = new IOException("IO stopped");
        MethodHandle checked = MethodHandles.throwException(
                void.class, IOException.class);
        try {
            checked.invokeExact(problem);
        } catch (IOException ex) {
            System.out.println("checked same instance: "
                    + (ex == problem));
            System.out.println("checked message: " + ex.getMessage());
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 --release 17 BaseHandleEdgesDemo.java
java BaseHandleEdgesDemo
```

Stdout:

```text
zero and empty: true
typed null: true
same mutable object: true
current contents: AB
identity void: rejected
constant void: rejected
invokeExact signature: rejected
checked same instance: true
checked message: IO stopped
```

**Điểm học được:**

- `zero(int.class)` và `empty(methodType(int.class))` cùng có `()int`, trả `0`.
- `constant(String.class, null)` tạo giá trị `null` có kiểu reference cụ thể.
- `constant(StringBuilder.class, buffer)` không sao chép `buffer`; thay đổi nội dung thành `AB` được thấy ở lần gọi sau.
- Hai factory `identity` và `constant` từ chối `void` ngay khi tạo.
- Truyền tham số `9` cho `fixed` kiểu `()int` gây `WrongMethodTypeException` **khi invoke**.
- `throwException(void.class, IOException.class)` vẫn ném chính checked exception được đưa vào, dù return type là `void`.

## 10. Chọn factory và adapter đúng nhu cầu

| Bài toán | Cách chọn | Điều cần tránh |
| --- | --- | --- |
| Nhánh luôn trả cấu hình `"OFF"` | `constant(String.class, "OFF")` | Đừng gọi bằng tham số nếu chưa `dropArguments`. |
| Bước transform tùy chọn không thay đổi input | `identity(T.class)` | Đừng tưởng nó clone mutable input. |
| Handler không được cấu hình nhưng được phép bỏ qua | `empty(expectedMethodType)` | Không dùng default `null`/`0` nếu nghiệp vụ cần báo lỗi. |
| Nhánh không hợp lệ phải dừng bằng lỗi | `throwException(R.class, E.class)` | Đừng tưởng nó tự tạo ngoại lệ. |
| Hàm không nhận input, trả default của kiểu `T` | `zero(T.class)` hoặc `empty(methodType(T.class))` | `constant(void.class,...)` không thay thế được `zero(void.class)`. |
| Nhánh hằng số cần nhận input giả | `dropArguments(constant(...),0,inputTypes...)` | Chữ ký các nhánh phải đồng bộ. |
| Nhánh lỗi cần exception cố định | `insertArguments(throwException(...),0,exception)` | Bind cùng exception cho mọi request có thể gây khó debug. |

### 10.1. Tình huống thực tế

**Router/dispatcher động:** nếu route đang bị tắt, nhánh trả mã lỗi hoặc ném ngoại lệ được dựng bằng handle nền có cùng signature với route đang bật. Tuy nhiên nếu “tắt” là trạng thái nghiệp vụ cần thống kê, một kết quả typed error có thể tốt hơn việc ném exception.

**Transformer chain:** một bước không áp dụng có thể dùng `identity(String.class)` để giữ nguyên dữ liệu thay vì tạo implementation `String passthrough(String s)`.

**Schema/serialization:** có thể dùng `empty(MethodType)` sinh một giá trị mặc định cho trường optional. Nếu thuộc tính bắt buộc thì mặc định `0`/`null` không an toàn; cần explicit validation hoặc nhánh ném.

**Dynamic runtime/DSL:** các factory tạo node `return constant`, `pass input`, `no-op` và `throw error` để graph được liên kết/đổi ở runtime. Ưu điểm là thể hiện hành vi nhỏ bằng handle đúng kiểu, không cần định nghĩa nhiều method Java phụ trợ.

## 11. Lỗi phổ biến và cách xử lý

| Lỗi | Dấu hiệu / lý do | Cách xử lý |
| --- | --- | --- |
| `constant(void.class, x)` hoặc `identity(void.class)` | `IllegalArgumentException` tại factory | Dùng `empty(methodType(void.class,...))` cho no-op. |
| `constant(int.class, "123")` | Không parse chuỗi thành primitive, có thể bị `ClassCastException` | Chuyển thành wrapper số hợp lệ trước khi tạo. |
| `constant(String.class, someStringBuilder)` | Kiểu giá trị không cast được sang String | Dùng `CharSequence.class` hoặc `someStringBuilder.toString()` phù hợp ý nghĩa. |
| Cố gọi handle `()T` với một đối số | `WrongMethodTypeException` khi `invokeExact` | Gọi 0 đối số hoặc dùng `dropArguments` để nhận input giả. |
| Call site `invokeExact` có return type sai | Signature mismatch dù số tham số đúng | Gắn cast/assignment đúng `h.type()`; chủ động dùng adapter khi cần. |
| Cho rằng `empty` ngăn cả side effect của đối số | Biểu thức của caller vẫn được tính | Không truyền biểu thức có side effect nếu không muốn nó chạy. |
| Dùng `empty` để báo một lỗi bắt buộc | Dòng xử lý sau nhận default `null`/`0` mà không biết lỗi | Dùng `throwException` hoặc một kết quả lỗi rõ ràng. |
| Chia sẻ handle constant giữ mutable object | Nhiều caller quan sát thay đổi không mong muốn | Immutable value hoặc defensive copy và quản lý thread-safety. |
| Cho rằng `throwException` tự khởi tạo exception | Cần truyền một exception object tại mỗi invocation | Tạo mới ở caller hoặc bind bằng adapter có chủ ý. |
| Ghép nhánh có chữ ký khác nhau | `IllegalArgumentException` ở combinator | In `type()` và điều chỉnh bằng `dropArguments` / `insertArguments` / `asType` có kiểm soát. |

### 11.1. Phân biệt thời điểm lỗi

- **Tại factory:** kiểu `void` không hợp lệ của `constant`/`identity`, giá trị không thể chuyển kiểu, `MethodType` không hợp lệ.
- **Tại combinator:** chữ ký giữa các nhánh không tương thích.
- **Tại invocation:** `invokeExact` sai descriptor ném `WrongMethodTypeException`; `throwException` thực sự ném object được truyền vào; `empty` trả mặc định.

Không nên catch mọi `Throwable` rồi biến thành một thông báo chung. Cần phân loại lỗi cấu hình graph, lỗi kiểu call site và ngoại lệ ứng dụng do nhánh thực sự sinh ra.

## 12. Hiệu năng, bảo mật và kiểm thử

**Hiệu năng:** các factory nền thường phù hợp để cache/tái sử dụng trong graph ổn định, nhưng không có cam kết mặc định rằng chúng nhanh hơn method hoặc lambda Java thông thường. JIT có thể tối ưu một chuỗi handle khi đủ điều kiện; đo workload thực tế bằng benchmark có warmup thay vì vài lần `nanoTime()`. Tránh tạo lại nhiều handle trong hot path nếu có thể chuẩn bị chúng tại bootstrap.

**Quyền và dữ liệu:** bốn factory này không cần `Lookup`, không tự truy cập private method. Nhưng `constant` có thể giữ object nhạy cảm, còn `throwException` có thể giữ exception chứa thông tin nhạy cảm. Chia sẻ handle là chia sẻ khả năng lấy giá trị/nhận lỗi theo nội dung đã bind. Cần kiểm soát đời sống tham chiếu, thread-safety và logging.

**Kiểm thử:** nên assert cả `type()` và giá trị/ngoại lệ. Bộ test tối thiểu phải cover kiểu primitive/reference/void, null reference, object mutable, checked exception, `invokeExact` sai chữ ký, và một combinator có nhánh thành công/thất bại. Những test này xác định rõ contract hơn việc chỉ kiểm thử một giá trị đầu ra.

## 13. Câu hỏi tự kiểm tra

**1. `constant(int.class, 10)` có thể nhận tham số `String` trực tiếp không?**

Không. Nó có chữ ký `()int`. Dùng `dropArguments(constant(int.class, 10), 0, String.class)` nếu muốn một handle `(String)int` bỏ qua String.

**2. `identity(String.class)` và `constant(String.class, "hello")` khác nhau thế nào?**

Identity có chữ ký `(String)String`, trả input ở mỗi lần gọi; constant có `()String` và trả giá trị đã gắn lúc tạo.

**3. Có thể tạo `empty(methodType(void.class, int.class))` không?**

Có. Handle `(int)void` nhận `int` rồi hoàn thành bình thường. Trái lại, `identity(void.class)` và `constant(void.class,...)` không hợp lệ.

**4. `empty(methodType(boolean.class, String.class))` nhận `"yes"` thì trả gì?**

Trả `false`. Nó không parse hoặc nhìn nội dung chuỗi; chỉ trả default của kiểu `boolean`.

**5. `throwException(String.class, IOException.class)` có thật sự tạo String kết quả không?**

Không. `String` là return type danh nghĩa của handle để ghép vào graph; khi invoke handle ném đối tượng IOException được truyền vào.

**6. `constant(StringBuilder.class, buffer)` có bảo đảm nội dung buffer không đổi không?**

Không. Nó giữ cùng reference chứ không clone. Thay đổi từ nơi khác có thể hiện ra ở lần gọi sau.

**7. Vì sao phải dùng `dropArguments` trước khi ghép constant vào nhánh `(boolean)String`?**

Vì constant gốc là `()String`. Adapter thêm tham số `boolean` bị bỏ qua, giúp nhánh mới có chữ ký phù hợp với graph.

## 14. Ghi nhớ

- **`constant(type,value)` → `()T`:** kết quả cố định, type không được `void`, có kiểm tra/chuyển giá trị lúc tạo.
- **`identity(type)` → `(T)T`:** một input, trả nguyên input, type không được `void`.
- **`empty(methodType)` → `(A...)R`:** nhận đúng chữ ký nhưng bỏ qua input, trả default hoặc hoàn thành `void`.
- **`throwException(returnType,exType)` → `(E)R`:** nhận một throwable rồi ném, không có đường trả bình thường; `R` là kiểu danh nghĩa.
- Các factory này **không cần `Lookup`**; phải kiểm tra chữ ký khi dùng `invokeExact` và khi ghép combinator.
- Bảo đảm semantics nghiệp vụ khi dùng mặc định/null, object mutable hay ngoại lệ được tái sử dụng.

### Tài liệu chính thức Java SE 17

- [`MethodHandles`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html): `constant`, `identity`, `empty`, `zero`, `throwException`, `dropArguments`, `insertArguments` và `guardWithTest`.
- [`MethodHandle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html): `type()`, `invokeExact`, `invoke` và mô hình signature-polymorphic.
- [`MethodType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html): biểu diễn kiểu tham số/kiểu trả về.
