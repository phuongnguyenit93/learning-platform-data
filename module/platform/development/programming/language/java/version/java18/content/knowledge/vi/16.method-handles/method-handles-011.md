# Bỏ qua kết quả trả về hoặc dùng var: kiểm chứng WrongMethodTypeException tại vị trí gọi

## 1. Vì sao lỗi xảy ra dù tham số truyền vào đúng?

`MethodHandle` là tham chiếu thực thi có kiểu rất cụ thể. Kiểu thực của nó được mô tả bằng `MethodType` gồm **toàn bộ kiểu tham số và kiểu trả về**. Khi gọi `invokeExact`, JVM yêu cầu kiểu của **vị trí gọi** (*call site*, được javac mã hóa thành symbolic method descriptor) trùng chính xác với `handle.type()`.

Điểm dễ bỏ sót: **kiểu trả về cũng nằm trong chữ ký cần khớp**. Việc bạn không dùng kết quả, hoặc viết `var` thay cho một cast cụ thể, có thể làm javac phát ra descriptor khác — ngay cả khi tên method và kiểu các đối số hoàn toàn đúng.

Tình huống trung tâm:

```java
MethodHandle add = MethodHandles.lookup().findStatic(
        Example.class,
        "add",
        MethodType.methodType(int.class, int.class, int.class));

// Target thực có kiểu (int, int)int.
int ok = (int) add.invokeExact(2, 3); // Khớp, trả 5.

add.invokeExact(2, 3);              // Sai: call site đòi (int,int)void.
var value = add.invokeExact(2, 3);   // Sai: call site đòi (int,int)Object.
```

Hai dòng sau **vẫn biên dịch** nhưng sẽ ném `WrongMethodTypeException` khi chạy. Điều này không có nghĩa `var` là lỗi hay JVM bị hỏng; đây là hợp đồng của API signature-polymorphic. Để sửa đúng:

```java
var value = (int) add.invokeExact(2, 3); // var suy ra int từ biểu thức cast.
```

Bài này thuộc nhóm `MethodHandle` trong lộ trình Java 18, nhưng tập trung hoàn toàn vào những quy tắc vẫn đúng trên JDK hiện đại. `MethodHandle.invokeExact`, `invoke`, `MethodType` và `asType` đều là API công khai còn được hỗ trợ.

**Sau khi học, bạn cần chứng minh được:**

- Vì sao lời gọi `invokeExact(...)` đứng riêng thành câu lệnh có return descriptor `void`.
- Vì sao `var result = handle.invokeExact(...)` suy ra `Object`, **không suy ra** kiểu trả về của target.
- Vì sao `(int) handle.invokeExact(...)` hay `(String) handle.invokeExact(...)` ảnh hưởng tới descriptor ở **vị trí gọi**, không chỉ là cast hậu kỳ thông thường.
- Cách phân biệt `invokeExact` với `invoke` và cách tạo adapter tường minh bằng `asType`.
- Cách dùng counter chứng minh target chưa hề chạy khi `WrongMethodTypeException` được ném trước khi thực thi.
- Cách kiểm chứng descriptor bằng `javap -c -p` mà không cần API JVM nội bộ.

## 2. Kiểu của handle khác kiểu javac ghi tại call site

Giả sử ta có:

```java
static int add(int left, int right) {
    return left + right;
}

MethodHandle handle = MethodHandles.lookup().findStatic(
        Example.class,
        "add",
        MethodType.methodType(int.class, int.class, int.class)
);
```

`handle.type()` báo kiểu:

```text
(int,int)int
```

Đây là **kiểu của handle**. Nhưng mỗi lần viết `handle.invokeExact(...)` trong source lại tạo **một call site riêng**. Java compiler ghi vào bytecode kiểu của từng đối số và kiểu kết quả mà biểu thức gọi yêu cầu.

| Cách viết trong Java | Return type của call site | Descriptor tượng trưng | Đối với handle `(int,int)int` |
| --- | --- | --- | --- |
| `(int) handle.invokeExact(2, 3)` | `int` | `(II)I` | Khớp, chạy |
| `handle.invokeExact(2, 3);` | `void` | `(II)V` | `WrongMethodTypeException` |
| `var x = handle.invokeExact(2, 3);` | `Object` | `(II)Ljava/lang/Object;` | `WrongMethodTypeException` |
| `Object x = handle.invokeExact(2, 3);` | `Object` | `(II)Ljava/lang/Object;` | `WrongMethodTypeException` |
| `var x = (int) handle.invokeExact(2, 3);` | `int` | `(II)I` | Khớp, `x` có kiểu `int` |
| `Object x = (Integer) handle.invokeExact(2, 3);` | `Integer` | `(II)Ljava/lang/Integer;` | Không khớp handle trả `int` |
| `handle.invoke(2, 3);` | `void` | `(II)V` | `invoke` có thể adapt để bỏ kết quả |
| `var x = handle.invoke(2, 3);` | `Object` | `(II)Ljava/lang/Object;` | `invoke` có thể box kết quả `int` thành `Integer` |

**Đọc descriptor:** `I` nghĩa là `int`, `V` nghĩa là `void`; `Ljava/lang/Object;` nghĩa là reference `java.lang.Object`. Trong bytecode, descriptor biểu diễn kiểu tham số rồi đến kiểu trả về. Ví dụ `(II)I` nghĩa là nhận hai `int` và trả một `int`.

Chú ý dòng `(Integer) handle.invokeExact(...)`: cast `Integer` không làm boxing theo cách `invokeExact`. Nó yêu cầu trực tiếp một call site trả `Integer`, không trùng handle trả primitive `int`.

### 2.1. Tại sao bỏ qua kết quả không giống Java method call thông thường?

Với method Java thông thường trả `int`, việc viết `add(2, 3);` hợp lệ: method vẫn chạy rồi giá trị trả về được bỏ qua. Nhưng với lời gọi signature-polymorphic `invokeExact`, một lần gọi **đứng riêng làm expression statement** được javac biên dịch với kiểu kết quả `void`. Nếu handle thật trả `int`, hai kiểu không khớp.

Đây là quy tắc **ở ngữ cảnh biên dịch**, không phải JVM tự ý bỏ một kết quả mà không có kiểm tra kiểu. Không nên suy diễn từ cú pháp giống nhau rằng hai dạng gọi hoàn toàn tương đương.

### 2.2. Tại sao var không tự lấy kiểu từ MethodHandle.type()?

`var` suy ra kiểu biến từ **kiểu tĩnh của biểu thức khởi tạo**. Khi viết `var x = handle.invokeExact(2, 3)`, biểu thức `invokeExact` không nằm trong cast, cũng không phải expression statement đứng riêng, vì vậy nó có kiểu kết quả `Object` theo quy tắc signature polymorphism.

Java compiler **không thực thi** `handle.type()` để suy ra kiểu `int`. Handle là đối tượng nhận được ở runtime và có thể thay đổi qua một biến/field; javac không biến kiểu runtime của nó thành static return type cho `var`.

`var x = (int) handle.invokeExact(2, 3)` khác ở chỗ **cast `(int)` nằm trực tiếp trên lời gọi**, khiến call-site descriptor trả `int`. Sau đó `var` mới suy ra kiểu `int` của biểu thức cast.

### 2.3. Đặt cast ở đâu mới quan trọng?

Đối với signature-polymorphic call, compiler lấy kiểu trả về từ **cast áp trực tiếp cho invocation expression**:

```java
var a = (int) handle.invokeExact(2, 3);          // (II)I
Object b = (int) handle.invokeExact(2, 3);       // (II)I rồi box int thành Integer
var c = (Object) handle.invokeExact(2, 3);       // (II)Object => mismatch
```

Dòng `b` đặc biệt quan trọng: biến được khai báo `Object` **không quyết định** return descriptor là `Object`, bởi cast `(int)` trực tiếp lên invocation đã quyết định return descriptor là `int`. Việc boxing/assignment diễn ra **sau** khi `invokeExact` chạy thành công.

## 3. invokeExact, invoke và asType: ba cách kiểm soát kiểu

| API | Hợp đồng kiểu | Cách dùng |
| --- | --- | --- |
| `invokeExact` | Call-site descriptor phải bằng chính xác `handle.type()`, kể cả return type; không adapt đối số/return | Khi biết kiểu chính xác, muốn kiểm tra sai kiểu rõ ràng |
| `invoke` | Nếu cần, chuyển đổi call-site type bằng quy tắc tương tự `handle.asType(callSiteType)` | Khi chủ động cho phép conversions như boxing, widening hay bỏ return |
| `asType(MethodType)` | Tạo handle đã được adapt có kiểu mới, nếu chuyển đổi hợp lệ | Khi muốn gọi nhiều lần với một kiểu ổn định |

Đối với handle `(int,int)int`:

```java
// Vẫn lỗi: call site của invokeExact là (int,int)void.
handle.invokeExact(2, 3);

// Adapt ngay lúc gọi; Java cho phép bỏ kết quả của invoke thường.
handle.invoke(2, 3);

// Tạo handle có return void thật, rồi dùng invokeExact ở statement context.
MethodHandle discard = handle.asType(
        MethodType.methodType(void.class, int.class, int.class));
discard.invokeExact(2, 3); // Khớp (int,int)void, target vẫn chạy.
```

`asType` không sửa handle ban đầu: `MethodHandle` là immutable, và `discard` là handle khác có `type()` bằng `(int,int)void`. Với adapter void, giá trị `int` mà target trả về được bỏ qua theo hợp đồng adaptation.

Với `invoke`, chuyển đổi không phải vô hạn: không đúng số đối số, không thể cast hoặc không thể adapt theo `asType` vẫn có thể ném `WrongMethodTypeException` hay exception khác tương ứng. Vì thế không thay hết `invokeExact` thành `invoke` chỉ để che sai kiểu.

## 4. Chương trình tự kiểm chứng: lỗi trước khi target được thực thi

Ví dụ này không cần thư viện ngoài hoặc module đặc biệt. Lưu thành file `ExactReturnContextLab.java` trong thư mục thực hành của bạn. Các method đích có counter để thấy rõ khi nào JVM thực sự chạy logic bên dưới.

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;
import java.util.concurrent.atomic.AtomicInteger;

public final class ExactReturnContextLab {
    private static final AtomicInteger ADD_CALLS = new AtomicInteger();
    private static final AtomicInteger LABEL_CALLS = new AtomicInteger();
    private static final AtomicInteger SIGNAL_CALLS = new AtomicInteger();

    private static int add(int left, int right) {
        ADD_CALLS.incrementAndGet();
        return left + right;
    }

    private static String label(int number) {
        LABEL_CALLS.incrementAndGet();
        return "id-" + number;
    }

    private static void signal(String value) {
        SIGNAL_CALLS.incrementAndGet();
    }

    @FunctionalInterface
    private interface ThrowingAction {
        void run() throws Throwable;
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static void expectWrong(
            String title, ThrowingAction action) throws Throwable {
        int addBefore = ADD_CALLS.get();
        int labelBefore = LABEL_CALLS.get();
        int signalBefore = SIGNAL_CALLS.get();

        try {
            action.run();
            throw new AssertionError(
                    "Đáng lẽ phải ném WrongMethodTypeException: " + title);
        } catch (WrongMethodTypeException expected) {
            // Nếu mismatch xảy ra tại call site, method đích chưa thực thi.
            check(ADD_CALLS.get() == addBefore,
                    "add() đã chạy trong ca sai kiểu: " + title);
            check(LABEL_CALLS.get() == labelBefore,
                    "label() đã chạy trong ca sai kiểu: " + title);
            check(SIGNAL_CALLS.get() == signalBefore,
                    "signal() đã chạy trong ca sai kiểu: " + title);
            System.out.println("EXPECTED WrongMethodTypeException: " + title);
        }
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        MethodHandle add = lookup.findStatic(
                ExactReturnContextLab.class,
                "add",
                MethodType.methodType(int.class, int.class, int.class));

        MethodHandle label = lookup.findStatic(
                ExactReturnContextLab.class,
                "label",
                MethodType.methodType(String.class, int.class));

        MethodHandle signal = lookup.findStatic(
                ExactReturnContextLab.class,
                "signal",
                MethodType.methodType(void.class, String.class));

        check(add.type().equals(
                MethodType.methodType(int.class, int.class, int.class)),
                "Sai MethodType của add");
        check(label.type().equals(
                MethodType.methodType(String.class, int.class)),
                "Sai MethodType của label");
        check(signal.type().equals(
                MethodType.methodType(void.class, String.class)),
                "Sai MethodType của signal");

        // A. Cast primitive trực tiếp: call site (int,int)int khớp.
        int exact = (int) add.invokeExact(2, 3);
        check(exact == 5 && ADD_CALLS.get() == 1,
                "invokeExact với cast int phải thành công");

        // B. var lấy kiểu từ biểu thức cast: var inferred là int.
        var inferred = (int) add.invokeExact(10, 20);
        check(inferred == 30 && ADD_CALLS.get() == 2,
                "var với cast int phải thành công");

        // C. Biến đích Object không sửa return type đã do cast quyết định.
        Object boxed = (int) add.invokeExact(3, 4);
        check(Integer.valueOf(7).equals(boxed)
                        && ADD_CALLS.get() == 3,
                "Cast int rồi boxing thành Object phải thành công");

        // D. Bỏ kết quả: call site (int,int)void KHÔNG khớp (int,int)int.
        expectWrong("discarded int result", () -> {
            add.invokeExact(2, 3);
        });

        // E. var không có cast: return type ở call site là Object.
        expectWrong("var without cast on int result", () -> {
            var unused = add.invokeExact(2, 3);
        });

        // F. Khai báo Object không tạo implicit boxing cho invokeExact.
        expectWrong("Object assignment on int result", () -> {
            Object unused = add.invokeExact(2, 3);
        });

        // G. Cast Object hoặc Integer vẫn yêu cầu sai return descriptor.
        expectWrong("cast Object on int result", () -> {
            var unused = (Object) add.invokeExact(2, 3);
        });
        expectWrong("cast Integer on int result", () -> {
            var unused = (Integer) add.invokeExact(2, 3);
        });

        // H. Thay đổi kiểu đối số cũng gây WrongMethodTypeException.
        expectWrong("long argument instead of int", () -> {
            int unused = (int) add.invokeExact(2L, 3);
        });
        check(ADD_CALLS.get() == 3,
                "Tất cả ca invokeExact mismatch phải dừng trước add()");

        // I. Handle trả String: cast String trực tiếp tạo (int)String.
        var tag1 = (String) label.invokeExact(8);
        Object tag2 = (String) label.invokeExact(9);
        check("id-8".equals(tag1) && "id-9".equals(tag2),
                "Exact call trả String phải thành công");
        check(LABEL_CALLS.get() == 2,
                "label() phải chạy đúng hai lần");

        expectWrong("var without cast on String result", () -> {
            var unused = label.invokeExact(10);
        });

        // J. Handle trả void: expression statement là kiểu đúng.
        signal.invokeExact("sent");
        check(SIGNAL_CALLS.get() == 1,
                "Handle trả void phải được gọi ở statement context");

        expectWrong("var on void result", () -> {
            var unused = signal.invokeExact("not-sent");
        });

        // K. invoke có thể adapt return value sang void/Object.
        add.invoke(4, 5); // int result bị bỏ qua sau adaptation.
        check(ADD_CALLS.get() == 4,
                "invoke với kết quả bỏ qua vẫn phải chạy add()");

        var flexible = add.invoke(5, 6); // Static type của var là Object.
        check(Integer.valueOf(11).equals(flexible)
                        && ADD_CALLS.get() == 5,
                "invoke có thể box int sang Object");

        // L. Adapt rõ kiểu handle để invokeExact ở statement context.
        MethodHandle discard = add.asType(
                MethodType.methodType(
                        void.class, int.class, int.class));
        check(discard.type().equals(
                MethodType.methodType(
                        void.class, int.class, int.class)),
                "asType phải tạo handle có return void");

        discard.invokeExact(7, 8);
        check(ADD_CALLS.get() == 6,
                "Adapter void phải gọi target và bỏ kết quả");

        check(add.type().returnType() == int.class,
                "asType không được thay đổi handle gốc");

        System.out.println("PASS: exact cast sets int/String return type");
        System.out.println("PASS: bare invokeExact requires void return");
        System.out.println("PASS: uncast var requires Object return");
        System.out.println("PASS: argument and return mismatch detected");
        System.out.println("PASS: mismatch does not execute target");
        System.out.println("PASS: invoke can adapt return");
        System.out.println("PASS: asType provides explicit void adapter");
        System.out.println("COUNTS add=" + ADD_CALLS.get()
                + ", label=" + LABEL_CALLS.get()
                + ", signal=" + SIGNAL_CALLS.get());
    }
}
```

### 4.1. Vì sao chương trình phân biệt được lỗi trước target?

Ba method đích `add`, `label`, `signal` đều tăng counter **ở dòng đầu tiên**. Hàm `expectWrong` ghi nhớ bộ đếm trước lời gọi sai, bắt đúng `WrongMethodTypeException` rồi xác nhận mọi counter **không đổi**.

Nếu một lời gọi sai thực sự chạy vào method đích trước khi ném lỗi, assertion sẽ thất bại. Với `invokeExact` mismatch, lỗi xảy ra ở bước kiểm tra **MethodType của receiver với call-site descriptor**, không phải lỗi do implementation của `add` gây ra.

Đây là phép thử hành vi qua API công khai, không yêu cầu đọc bytecode của JDK hoặc can thiệp JVM.

### 4.2. Kết quả mong đợi

```text
EXPECTED WrongMethodTypeException: discarded int result
EXPECTED WrongMethodTypeException: var without cast on int result
EXPECTED WrongMethodTypeException: Object assignment on int result
EXPECTED WrongMethodTypeException: cast Object on int result
EXPECTED WrongMethodTypeException: cast Integer on int result
EXPECTED WrongMethodTypeException: long argument instead of int
EXPECTED WrongMethodTypeException: var without cast on String result
EXPECTED WrongMethodTypeException: var on void result
PASS: exact cast sets int/String return type
PASS: bare invokeExact requires void return
PASS: uncast var requires Object return
PASS: argument and return mismatch detected
PASS: mismatch does not execute target
PASS: invoke can adapt return
PASS: asType provides explicit void adapter
COUNTS add=6, label=2, signal=1
```

Đoạn ví dụ không đặt tên method trùng `invokeExact` hay dùng reflection `Method.invoke` để gọi `MethodHandle.invokeExact`. Lời gọi trong source phải thực sự được javac nhận diện là **signature-polymorphic invocation**.

## 5. Thực thi trên JDK 18+ và xem descriptor

Từ thư mục chứa `ExactReturnContextLab.java`:

### Windows PowerShell

```powershell
java -version
javac --release 18 ExactReturnContextLab.java
java ExactReturnContextLab

# Xem bytecode của main và các lambda trong class.
javap -c -p ExactReturnContextLab
```

### Bash/Linux/macOS

```bash
java -version
javac --release 18 ExactReturnContextLab.java
java ExactReturnContextLab

javap -c -p ExactReturnContextLab
```

`--release 18` giới hạn việc sử dụng cú pháp và API vào tập tương thích Java 18, còn cách gọi `java` dùng JDK runtime hiện có. Nếu JDK đang dùng không hỗ trợ biên dịch `--release 18`, phải dùng JDK phù hợp thay vì âm thầm hạ mục tiêu của bài.

### 5.1. Đọc output javap

Tìm các lệnh `invokevirtual` trỏ đến `java/lang/invoke/MethodHandle.invokeExact`. Thứ tự, số thứ tự constant pool và tên synthetic method có thể khác theo compiler, nhưng các descriptor quan trọng là:

```text
// Cast int ngay trên invocation.
MethodHandle.invokeExact:(II)I

// Bỏ qua giá trị bằng expression statement.
MethodHandle.invokeExact:(II)V

// var hoặc Object assignment không có cast.
MethodHandle.invokeExact:(II)Ljava/lang/Object;

// Cast String ngay trên handle trả String.
MethodHandle.invokeExact:(I)Ljava/lang/String;

// Handle void được gọi thành statement.
MethodHandle.invokeExact:(Ljava/lang/String;)V
```

Phần `invokeExact` bên trong lambda thường nằm trong các method do compiler sinh ra, chẳng hạn `lambda$main$0`. Vì vậy cần dùng `javap -p` để xem private/synthetic methods. Đừng chỉ tìm đúng tên `main` rồi kết luận không có descriptor sai.

Nếu bạn thấy `(II)V` cạnh một lời gọi từ handle `(int,int)int`, nguyên nhân `WrongMethodTypeException` đã hiện rõ mà không cần stack trace dài: kiểu trả về đòi hỏi ở call site là `void`, khác `int` của handle.

## 6. Đối chứng có chủ đích: khi var không cần cast vẫn đúng

`var` **không sai tự thân**. `var` chỉ gây mismatch trong ví dụ vì nó làm call site mong đợi `Object`, trong khi handle gốc trả `int` hoặc `String`. Nếu handle **thực sự trả `Object`**, câu lệnh `var x = handle.invokeExact(...)` hoàn toàn có thể chạy đúng.

Ví dụ tạo một adapter tường minh:

```java
MethodHandle add = MethodHandles.lookup().findStatic(
        ExactReturnContextLab.class,
        "add",
        MethodType.methodType(int.class, int.class, int.class));

// Adapter mới có type (int,int)Object và box kết quả int.
MethodHandle boxedReturn = add.asType(
        MethodType.methodType(Object.class, int.class, int.class));

// var suy ra Object; call site cũng đòi Object => khớp boxedReturn.type().
var value = boxedReturn.invokeExact(4, 6);

// value có static type Object, giá trị thực là Integer(10).
if (!Integer.valueOf(10).equals(value)) {
    throw new AssertionError("Không nhận được giá trị boxed");
}
```

Đoạn này là **biến thể độc lập** để đưa vào trong cùng lớp đã định nghĩa phương thức `add`, hoặc điều chỉnh `Lookup` phù hợp. Không phải chép nguyên nó thành một Java file bên ngoài rồi giả định private method của `ExactReturnContextLab` có thể truy cập từ mọi lớp.

Tương tự, nếu handle gốc trả `String`:

```java
String text = (String) stringHandle.invokeExact(4); // (I)String, đúng.
var text2 = (String) stringHandle.invokeExact(5); // var suy ra String, đúng.

// Nếu viết var text3 = stringHandle.invokeExact(6),
// call site mong đợi Object nên sai với handle trả String.
```

**Quy tắc cần nhớ:** không phải “luôn phải viết cast” mà là “**kiểu trả về được yêu cầu tại call site phải đúng `handle.type().returnType()`**”. Cast là một phương tiện để quy định kiểu của call site; adapter `asType` là một phương tiện khác để đổi kiểu handle có chủ đích.

### 6.1. Trường hợp void: bỏ qua kết quả mới là cách đúng

Nếu method đích trả `void`:

```java
MethodHandle notifier = MethodHandles.lookup().findStatic(
        Example.class,
        "notify",
        MethodType.methodType(void.class, String.class));

notifier.invokeExact("event"); // (String)void: khớp.

// var ignored = notifier.invokeExact("event");
// (String)Object: không khớp (String)void.
```

Đây là đối chứng quan trọng với handle trả `int`: **bỏ kết quả chỉ phù hợp với `invokeExact` khi kiểu trả về của handle thật là `void`** (hoặc đã tạo adapter void bằng `asType`).

### 6.2. Chuyển đổi khi invoke khác invokeExact

`invokeExact` không tự box primitive return chỉ vì biến nhận là `Object`. `invoke` thì có thể thực hiện adaptation tương đương `asType` nếu hợp lệ:

```java
MethodHandle add = /* handle có type (int,int)int */;

// Lời gọi không có cast: Object return ở call site.
// invoke cố gắng adapt (int,int)int -> (int,int)Object.
var boxed = add.invoke(3, 5); // Giá trị thực Integer(8).

// Expression statement có call-site return void;
// invoke có thể bỏ return int sau khi target chạy.
add.invoke(3, 5);
```

Nhưng `invoke` không làm mọi kiểu tương thích. Ví dụ chuyển đổi kiểu tham số không hợp lệ có thể thất bại theo hợp đồng `asType`. Do đó hãy đọc `handle.type()` và quyết định rõ cần exact invocation hay adaptation.

## 7. Những lỗi thường bị nhầm với WrongMethodTypeException

### 7.1. Thiếu cast trong khai báo có kiểu tường minh có thể là lỗi biên dịch

Xét handle trả `int`:

```java
// Ví dụ cố ý không biên dịch:
int n = add.invokeExact(1, 2);
```

Trong trường hợp này, `invokeExact` có kiểu tĩnh `Object` khi không có cast trực tiếp. Java không tự unbox `Object` sang `int` cho phép gán, vì vậy **javac có thể từ chối trước khi chạy**. Đừng hứa rằng mọi cách viết thiếu cast đều ném `WrongMethodTypeException` lúc runtime.

So sánh với:

```java
Object n = add.invokeExact(1, 2); // Biên dịch, nhưng runtime mismatch.
var m = add.invokeExact(1, 2);    // Biên dịch, nhưng runtime mismatch.
int k = (int) add.invokeExact(1, 2); // Biên dịch và chạy đúng.
```

Dòng đầu và dòng thứ hai tạo call site trả `Object`; dòng cuối tạo call site trả `int`. Kết luận dựa trên **biểu thức thực sự được javac biên dịch**, không chỉ nhìn kiểu biến ở vế trái.

### 7.2. WrongMethodTypeException khác ClassCastException

- `WrongMethodTypeException` của `invokeExact` cho biết call-site descriptor **không bằng** `MethodHandle.type()`. Mismatch có thể ở số/kiểu tham số hoặc return type.
- `ClassCastException` có thể phát sinh **sau** một phép chuyển kiểu tham chiếu không hợp lệ, hoặc trong adaptation khi giá trị runtime không phù hợp.
- `IllegalAccessException` thường xuất hiện khi **tạo handle bằng `Lookup.findStatic`/`findVirtual`** mà caller không có quyền truy cập member; đó là vấn đề lookup/access, không phải lỗi return context của `invokeExact`.
- Exception do method đích tự ném được truyền qua method handle; đó là lỗi của target, không nhất thiết là `WrongMethodTypeException`.

`MethodHandle.invokeExact` được khai báo `throws Throwable`. Vì vậy ví dụ `main` dùng `throws Throwable` và helper lambda cũng cho phép `throws Throwable`. Trong ứng dụng thật, hãy bắt/khai báo lỗi phù hợp thay vì dùng `catch (Exception ignored)` làm mất thông tin.

### 7.3. Đối số cũng phải khớp kiểu chính xác

Đừng nhìn mỗi return type. Với handle `(int,int)int`:

```java
int a = (int) add.invokeExact(1, 2);  // đúng
int b = (int) add.invokeExact(1L, 2); // sai: (long,int)int
```

`1` là literal `int`, còn `1L` là `long`. `invokeExact` không tự thu hẹp `long` về `int`. Tương tự, giá trị `Integer` so với primitive `int` ở vị trí đối số cũng có thể tạo descriptor khác.

Với signature-polymorphic methods, khi truyền literal `null` **không có cast**, JLS có quy tắc descriptor riêng liên quan đến kiểu `Void`; hãy cast tường minh như `(String) null` nếu cần caller type `String`. Đừng đặt kỳ vọng rằng null sẽ tự suy ra parameter type từ target handle.

### 7.4. Học từ bytecode, không nhìn mỗi exception message

Text của `WrongMethodTypeException` thường cho biết hai dạng MethodType không khớp, nhưng định dạng message không phải hợp đồng để test. Đừng assert chính xác chuỗi exception message trên mọi bản JDK.

Hãy kiểm tra:

1. `handle.type()` là gì?
2. Vị trí gọi có cast trực tiếp trên invocation hay không?
3. Lời gọi là expression statement hay biểu thức có giá trị?
4. Kiểu tĩnh từng đối số là `int`, `long`, `String`, `Object` hay kiểu khác?
5. Nếu cần, xem descriptor bằng `javap -c -p`.

Các câu hỏi đó xác định **nguyên nhân** thay vì chỉ đoán từ thông báo lỗi.

## 8. Bài tập biến thể để hiểu đúng ngữ cảnh gọi

### Bài tập A — chuyển một câu lệnh đang lỗi thành đúng mà không đổi target

Cho handle `(int,int)int` và source:

```java
handle.invokeExact(9, 1);
```

Hãy sửa theo **hai cách khác nhau**:

1. Giữ handle gốc, dùng kết quả với cast `(int)`.
2. Không cần kết quả, tạo adapter `handle.asType(methodType(void.class, int.class, int.class))` rồi gọi `invokeExact` như expression statement.

**Đáp án gợi ý:**

```java
int unused = (int) handle.invokeExact(9, 1);

MethodHandle discard = handle.asType(
        MethodType.methodType(void.class, int.class, int.class));
discard.invokeExact(9, 1);
```

Cả hai cách đều chạy target và bỏ được giá trị nếu không dùng tiếp biến `unused`. Khác biệt là cách thứ hai tạo handle thật có return type `void`.

### Bài tập B — lý giải ba biến var

Dự đoán và giải thích:

```java
var a = handle.invokeExact(1, 2);
var b = (int) handle.invokeExact(1, 2);
var c = handle.invoke(1, 2);
```

Với `handle.type() == (int,int)int`:

- `a` có static type `Object` và ném `WrongMethodTypeException`.
- `b` có static type `int` và thành công, nhận tổng.
- `c` có static type `Object` và có thể thành công nhờ `invoke` chuyển `int` thành `Integer`.

### Bài tập C — biến Java type nhưng không đổi target type

So sánh:

```java
Object first = (int) handle.invokeExact(2, 3);
Object second = (Object) handle.invokeExact(2, 3);
```

Vì sao `first` thành công và `second` thất bại? Giải thích bằng bytecode call-site descriptor `(II)I` so với `(II)Ljava/lang/Object;`, không giải thích bằng tên biến `Object`.

### Bài tập D — test phương thức không có giá trị trả về

Tạo handle trỏ tới method `void signal(String)` và kiểm tra:

```java
signalHandle.invokeExact("a");
var result = signalHandle.invokeExact("b");
```

Dự đoán số lần method `signal` thực sự được gọi (chỉ **1**), rồi thêm `AtomicInteger` để kiểm chứng rằng lần thứ hai lỗi trước khi target chạy.

### Bài tập E — kiểm tra kiểu đối số

Thay hai literal `int` bằng một literal `long` và một `int` nhưng giữ cast return `(int)`. Dự đoán `WrongMethodTypeException` do parameter descriptor mismatch; sau đó sửa bằng cách truyền đúng `int` hoặc chủ động tạo adapter thích hợp.

## 9. Checklist khi review mã MethodHandle

- [ ] In hoặc assert `handle.type()` trước khi viết `invokeExact`.
- [ ] Ghi đầy đủ **parameter types và return type**; không bỏ qua phần return trong `MethodType`.
- [ ] Với handle trả primitive, đặt cast primitive **trực tiếp** trên invocation khi muốn giữ kiểu exact.
- [ ] Với handle trả reference, đặt cast về đúng reference type của handle nếu cần exact return descriptor.
- [ ] Không viết `var x = invokeExact(...)` thiếu cast rồi hy vọng `var` suy ra return type của handle.
- [ ] Không bỏ kết quả trả về của non-void handle bằng lời gọi `invokeExact` đứng riêng.
- [ ] Nếu cần bỏ kết quả, dùng `invoke` hoặc adapter `asType(...void...)` có chủ đích.
- [ ] Nếu handle thật trả `void`, gọi `invokeExact` bằng expression statement.
- [ ] Kiểm tra kiểu **đối số tại call site**: `int` không tự đồng nhất với `long` hoặc `Integer`.
- [ ] Phân biệt mismatch ở `invokeExact` với compile-time type error và exception của target.
- [ ] Có thể đọc `javap -c -p` để thấy descriptor `(II)I`, `(II)V`, `(II)Ljava/lang/Object;`.
- [ ] Unit test bắt đúng `WrongMethodTypeException` và xác minh target không bị gọi.
- [ ] Không assert message cụ thể của exception hay phụ thuộc các class nội bộ của JDK.
- [ ] Ví dụ được biên dịch với `javac --release 18` trên JDK hỗ trợ Java 18.

**Tiêu chí hoàn thành:** Bạn giải thích được vì sao bỏ kết quả và dùng `var` tạo hai call sites khác nhau, viết lại chúng đúng hợp đồng `invokeExact` và chứng minh runtime mismatch xảy ra **trước** code của method đích.

## 10. Tài liệu tham khảo

- [MethodHandle — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandle.html): mục *Method handle compilation* và *Method handle invocation*, `invokeExact`, `invoke`, `asType` và return type của call site.
- [MethodType — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodType.html): biểu diễn parameter types, return type và sự bằng nhau của MethodType.
- [WrongMethodTypeException — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/WrongMethodTypeException.html): exception khi call site không tương thích với method handle.
- [Java Language Specification `15.12.3 — Java SE 25](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.12.3): quy tắc compile-time result của signature-polymorphic methods, gồm expression statement, cast và `Object`.
- [Java Language Specification `14.8 — Java SE 25](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.8): expression statements và ngữ cảnh dùng biểu thức gọi method.
- [javap tool — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javap.html): disassemble bytecode để đọc method descriptors ở call sites.
