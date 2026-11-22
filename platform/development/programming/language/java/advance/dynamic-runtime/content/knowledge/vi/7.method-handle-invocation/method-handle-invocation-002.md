# 7.2 `invokeExact`: khớp chính xác cả kiểu đối số và kiểu kết quả

`java.lang.invoke.MethodHandle` là một tham chiếu có kiểu tới thao tác có thể gọi ở thời điểm chạy. Khi dùng `invokeExact(...)`, JVM yêu cầu **kiểu của toàn bộ điểm gọi (call site)** phải **trùng chính xác** với `MethodType` của handle: **số lượng tham số, kiểu của từng tham số theo đúng thứ tự và cả kiểu trả về**. Kiểu giá trị lúc chạy có vẻ tương thích, hoặc Java có thể tự boxing/widening trong một lời gọi method thông thường, đều không đủ để vượt qua yêu cầu này.

Ví dụ: một handle có `type() == (int,int)int` chỉ được gọi qua `invokeExact` với đúng hai đối số có kiểu tĩnh `int` và một call site yêu cầu **kết quả `int`**. Nếu call site yêu cầu `long`, `Object` hay `void`, JVM ném `WrongMethodTypeException`, dù hai số đầu vào vẫn là `int`.

Bài này tập trung vào cơ chế **exact matching tại call site** và cách viết Java 17+ đúng, giúp bạn xử lý lỗi mà không vô tình làm mất tính kiểm tra kiểu của `invokeExact`.

Sau khi học, bạn có thể:

- Đọc `handle.type()` và giải thích đầy đủ dạng `(parameterTypes)returnType`.
- Hiểu compiler suy ra **kiểu tham số từ biểu thức đối số** và **kiểu kết quả từ cast trực tiếp hoặc ngữ cảnh statement**.
- Nhận diện mismatch ở argument, reference subtype, primitive/wrapper, receiver và return type.
- Phân biệt `invokeExact`, `invoke` và adapter `asType`; chọn cách sửa phù hợp.
- Viết code gọi static/virtual method handles, handle trả `void`, helper có chữ ký cụ thể, và chẩn đoán `WrongMethodTypeException`.
- Chạy, quan sát và giải thích hai ví dụ Java 17+ với stdout xác định.

## 1. `MethodType` bao gồm cả kết quả

Mỗi `MethodHandle` có một `java.lang.invoke.MethodType` bất biến, được đọc bằng `type()`. Về mặt mô hình:

```text
              [tham số đầu vào]     [kiểu kết quả]
(int, int)int         int,int   ->       int
(String)String        String    ->       String
(String)void          String    ->       void
(String,int)String    String,int->       String
```

`MethodType` mô tả **kiểu của chính handle**, không phải kiểu của một instance cụ thể được đưa vào lúc chạy. Nó chứa `Class<?>` cho mỗi parameter và return, có thể phân biệt `int.class` với `Integer.class`, `String.class` với `CharSequence.class`, và `void.class` với `Void.class`.

Ví dụ khai báo một method và tra handle:

```java
static int add(int a, int b) {
    return a + b;
}

MethodHandle h = MethodHandles.lookup().findStatic(
        Example.class, "add",
        MethodType.methodType(int.class, int.class, int.class));
```

Hai đoạn là **mã minh họa** đặt trong class `Example` và cần import `java.lang.invoke.*` hoặc các lớp tương ứng, xử lý ngoại lệ lookup. Phương thức `methodType` nhận **return type trước**, rồi đến các parameter types. `h.type().toString()` có dạng:

```text
(int,int)int
```

Ba chữ `int` trong `methodType(int.class, int.class, int.class)` lần lượt là **return**, **đối số thứ nhất**, **đối số thứ hai**. Đừng nhầm vị trí đầu tiên là tham số thứ nhất.

Một lời gọi chính xác:

```java
int value = (int) h.invokeExact(2, 3);
```

Compiler tạo điểm gọi với descriptor `(int,int)int`; kết quả trả về là `5`. Cast `(int)` ở ngay trước **biểu thức `h.invokeExact(...)`** không chỉ đổi kiểu biểu thức ở source: nó giúp compiler đặt **kiểu kết quả mong muốn** vào descriptor của điểm gọi.

## 2. Kiểm tra diễn ra tại call site, không tự thích nghi kiểu

`invokeExact` là một **signature-polymorphic method**. Trong bytecode của lời gọi, compiler ghi một descriptor dựa trên **kiểu tĩnh** của các đối số và kiểu kết quả theo ngữ cảnh gọi. JVM so sánh descriptor đó với `h.type()`. Hai phía phải tương đương chính xác; không có boxing, unboxing, widening hay downcast tự động trong quá trình exact invocation.

```text
Java source:
    int result = (int) h.invokeExact(2, 3);
                         |
                         v
Compiler ghi call-site descriptor: (int,int)int
                         |
                         v
Runtime đọc handle.type():        (int,int)int
                         |
             equality? yes ------+------> gọi target
                         |
             equality? no --------------> WrongMethodTypeException
```

Mặc dù Java thường cho phép truyền `int` vào method nhận `long`, quy tắc đó là **method invocation conversion của lời gọi method thông thường**; nó không thay thế điều kiện type equality của `invokeExact`.

Bảng này giả sử `h.type()` là `(int,int)int`:

| Mã tại call site | Descriptor quan trọng | Kết quả |
| --- | --- | --- |
| `int x = (int) h.invokeExact(2, 3);` | `(int,int)int` | **Đúng**, `x = 5` |
| `long x = (long) h.invokeExact(2, 3);` | `(int,int)long` | **Sai** kiểu trả về |
| `int x = (int) h.invokeExact(2L, 3);` | `(long,int)int` | **Sai** kiểu đối số thứ nhất |
| `Object x = (Object) h.invokeExact(2, 3);` | `(int,int)Object` | **Sai** kiểu trả về |
| `h.invokeExact(2, 3);` dưới dạng statement | `(int,int)void` | **Sai** vì handle trả `int` |
| `long x = (int) h.invokeExact(2, 3);` | `(int,int)int` | **Đúng**: Java widening kết quả sau lời gọi |
| `Object x = (int) h.invokeExact(2, 3);` | `(int,int)int` | **Đúng**: Java boxing sau lời gọi |
| `int x = (int) h.invokeExact((int) 2L, 3);` | `(int,int)int` | **Đúng**: cast đối số trước lời gọi |

Các dòng “sai” ở bảng là **mismatch runtime** và ném `java.lang.invoke.WrongMethodTypeException`; chúng thường **biên dịch được** vì `invokeExact` là signature polymorphic. Khác với lời gọi method Java thông thường, compiler không dùng chữ ký target để tự biến đổi từng đối số.

### 2.1. Vì sao kiểu kết quả cũng phải chính xác?

Đây là điểm dễ bỏ sót nhất. Nhiều người kiểm tra `h.type().parameterArray()` hoặc đếm argument, thấy đúng rồi nhưng vẫn nhận `WrongMethodTypeException`. Nguyên nhân là descriptor của JVM có **return type**, và `invokeExact` bắt buộc return type cũng phải khớp.

Ví dụ:

```java
// h.type() == (int,int)int
long wrong = (long) h.invokeExact(2, 3);   // WrongMethodTypeException
long right = (int) h.invokeExact(2, 3);    // Thành công: int được widen sau khi gọi
```

Dòng thứ hai không ép handle trả `long`; nó yêu cầu handle trả **`int`**, sau đó Java gán kết quả `int` vào biến `long` bằng conversion thông thường ở **ngoài** call site.

Tương tự:

```java
// h.type() == (int,int)int
Object wrong = (Object) h.invokeExact(2, 3); // WrongMethodTypeException
Object right = (int) h.invokeExact(2, 3);    // Integer boxing sau invokeExact
```

Việc muốn giữ kết quả trong biến `Object` **không** biến return type của handle thành `Object`. Chuyển kiểu kết quả sau khi exact call là một chuyện khác với yêu cầu chính `invokeExact` trả về `Object`.

### 2.2. Khi không cast trực tiếp, compiler làm gì?

Quy tắc tại Java source:

- Nếu lời gọi `invokeExact(...)` là **operand trực tiếp của một cast**, kiểu đích của cast quyết định return type tại call site (sau erasure khi cần).
- Nếu lời gọi được dùng như **expression statement** độc lập, return type tại call site là **`void`**.
- Nếu lời gọi được dùng như một biểu thức **không có cast trực tiếp**, return type được suy ra là **`Object`** theo quy tắc signature-polymorphic của API này.

Vì vậy đừng chỉ nhìn kiểu biến bên trái dấu `=` và hy vọng compiler tự chọn return type đó. Cách dễ đọc, dễ kiểm tra và ít lỗi nhất với `invokeExact` là đặt cast kiểu trả về **ngay trên lời gọi**, ví dụ `(int) h.invokeExact(...)` hoặc `(String) h.invokeExact(...)`.

## 3. Chương trình Java 17+ đầy đủ: đúng kiểu và bốn dạng mismatch

Tạo tệp **`InvokeExactDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;

public class InvokeExactDemo {
    private static int add(int left, int right) {
        return left + right;
    }

    private static String wrap(String value) {
        return "[" + value + "]";
    }

    private static void announce(String message) {
        System.out.println("announce: " + message);
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodHandle add = lookup.findStatic(
                InvokeExactDemo.class, "add",
                MethodType.methodType(int.class, int.class, int.class));
        System.out.println("add.type: " + add.type());
        int sum = (int) add.invokeExact(10, 20);
        System.out.println("sum: " + sum);

        try {
            long wrongReturn = (long) add.invokeExact(10, 20);
            System.out.println(wrongReturn);
        } catch (WrongMethodTypeException e) {
            System.out.println("wrong return: " + e.getClass().getSimpleName());
        }

        try {
            int wrongArgument = (int) add.invokeExact(10L, 20);
            System.out.println(wrongArgument);
        } catch (WrongMethodTypeException e) {
            System.out.println("wrong argument: " + e.getClass().getSimpleName());
        }

        try {
            add.invokeExact(10, 20);
        } catch (WrongMethodTypeException e) {
            System.out.println("discarded result: " + e.getClass().getSimpleName());
        }

        MethodHandle wrap = lookup.findStatic(
                InvokeExactDemo.class, "wrap",
                MethodType.methodType(String.class, String.class));
        String input = "Ada";
        String wrapped = (String) wrap.invokeExact(input);
        System.out.println("wrap.type: " + wrap.type());
        System.out.println("wrapped: " + wrapped);

        CharSequence broader = "Bea";
        try {
            String wrongReference = (String) wrap.invokeExact(broader);
            System.out.println(wrongReference);
        } catch (WrongMethodTypeException e) {
            System.out.println("wrong reference: " + e.getClass().getSimpleName());
        }

        MethodHandle adapted = add.asType(
                MethodType.methodType(long.class, int.class, int.class));
        System.out.println("adapted.type: " + adapted.type());
        long widened = (long) adapted.invokeExact(10, 20);
        System.out.println("adapted result: " + widened);

        long flexible = (long) add.invoke(10, 20);
        System.out.println("invoke result: " + flexible);

        MethodHandle announce = lookup.findStatic(
                InvokeExactDemo.class, "announce",
                MethodType.methodType(void.class, String.class));
        announce.invokeExact("done");
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac --release 17 InvokeExactDemo.java
java InvokeExactDemo
```

**Stdout đã được kiểm tra bằng biên dịch/chạy Java thực tế:**

```text
add.type: (int,int)int
sum: 30
wrong return: WrongMethodTypeException
wrong argument: WrongMethodTypeException
discarded result: WrongMethodTypeException
wrap.type: (String)String
wrapped: [Ada]
wrong reference: WrongMethodTypeException
adapted.type: (int,int)long
adapted result: 30
invoke result: 30
announce: done
```

### Phân tích lần lượt

1. `lookup.findStatic(...)` lấy handle cho `private static int add(int,int)`. `lookup` nằm trong chính `InvokeExactDemo` nên có quyền đối với private method của class mình.
2. `(int) add.invokeExact(10, 20)` tạo call-site `(int,int)int`, trùng với `add.type()`, trả `30`.
3. `(long) add.invokeExact(10, 20)` có return `long`, sai với return `int` của handle: `WrongMethodTypeException`.
4. `(int) add.invokeExact(10L, 20)` có argument đầu `long`, sai với `int`: `WrongMethodTypeException`.
5. `add.invokeExact(10, 20);` đứng độc lập như statement nên caller yêu cầu return `void`, cũng sai với `int`.
6. `wrap` nhận đúng `String`, trả đúng `String`; lời gọi với biến `String input` thành công.
7. `CharSequence broader` trỏ tới một object là `String`, nhưng kiểu **tĩnh** của biểu thức argument là `CharSequence`. Descriptor `(CharSequence)String` không trùng `(String)String`; object thực tế không làm `invokeExact` tự ép kiểu.
8. `add.asType((int,int)long)` tạo một **handle mới** có thể widen kết quả `int` của target thành `long`. Caller bây giờ yêu cầu `long`, và khớp với `adapted.type()`.
9. `add.invoke(10,20)` có cơ chế conversion linh hoạt tương đương việc dùng `asType` khi cần, nên `(int,int)long` có thể làm việc với target `(int,int)int`.
10. `announce` có kiểu `(String)void`; khi gọi `announce.invokeExact("done");` như một statement, caller cũng có return `void`. Đây là cách gọi đúng cho method trả `void`.

Những `try/catch` trong ví dụ chỉ minh họa **mismatch có chủ đích**. Trong code thật, không nên chủ động gọi sai rồi bắt `WrongMethodTypeException` để tìm cách gọi đúng. Hãy kiểm tra `handle.type()` và sửa chữ ký ngay từ nơi thiết kế lời gọi.

## 4. Đối số dùng kiểu tĩnh, không dùng kiểu của object lúc chạy

Đối với handle `(String)String`:

```java
String exact = "hello";
CharSequence broad = "hello";
Object generic = "hello";
```

Ba biến cùng có thể tham chiếu đến một đối tượng `String`, nhưng với `invokeExact` chúng không tương đương:

```java
// h.type() == (String)String
String a = (String) h.invokeExact(exact);          // đúng
String b = (String) h.invokeExact(broad);          // WrongMethodTypeException
String c = (String) h.invokeExact(generic);        // WrongMethodTypeException
String d = (String) h.invokeExact((String) broad); // đúng nếu value thực sự là String
```

Đây là **đoạn minh họa**, giả sử `h` đã được khởi tạo với `MethodType` tương ứng. Cast `(String) broad` diễn ra **trước invocation**, đổi static argument type thành `String`. Nếu object không phải `String`, Java có thể ném `ClassCastException` ở cast đó, trước khi handle được gọi; không phải `WrongMethodTypeException`.

### 4.1. Primitive vs wrapper và widening

Giả sử `h.type() == (int,int)int`:

```java
int a = 1;
Integer boxed = 1;
short small = 2;

int ok = (int) h.invokeExact(a, 2);                  // đúng
int noBox = (int) h.invokeExact(boxed, 2);           // sai: (Integer,int)int
int noWiden = (int) h.invokeExact(small, 2);         // sai: (short,int)int
int fixedBox = (int) h.invokeExact(boxed.intValue(), 2); // đúng
int fixedShort = (int) h.invokeExact((int) small, 2);    // đúng
```

Điểm quan trọng: `Integer` không được tự unbox thành `int` **bên trong** `invokeExact`; `short` không được tự widen thành `int`. Nếu yêu cầu conversion, làm nó **tường minh trước lời gọi** hoặc tạo adapter có kiểu mong muốn.

Một literal số nguyên như `2` mặc định có kiểu `int`; `2L` có kiểu `long`. Chúng tạo call-site descriptor khác nhau dù cùng biểu diễn số hai.

### 4.2. `null` và kiểu tham chiếu

Literal `null` trần trong lời gọi signature-polymorphic có quy tắc kiểu đặc biệt và không thể mặc nhiên hiểu là `String`. Khi handle mong đợi `String`, truyền `(String) null` nếu `null` có ý nghĩa hợp lệ với target:

```java
// h.type() == (String)String
String value = (String) h.invokeExact((String) null);
```

Lời gọi trên **qua được bước exact type check**, vì parameter type được biểu diễn là `String`. Tuy nhiên, target method có thể ném `NullPointerException` khi xử lý giá trị null. **Đúng MethodType không bảo đảm dữ liệu nghiệp vụ hợp lệ**.

### 4.3. Mảng và generic erasure

Nếu handle nhận `String[]`, call site phải dùng expression có static type `String[]`; một biến `Object[]` thực tế trỏ tới `String[]` vẫn làm call-site descriptor không trùng. Với method nhận `java.util.List<String>`, `MethodType` dùng `List.class` vì erasure; không có `List<String>.class`.

Tương tự, một handle nhận `Object` sẽ **không** tự chấp nhận biến có kiểu tĩnh `String` qua `invokeExact`:

```java
// h.type() == (Object)Object
Object response = (Object) h.invokeExact((Object) "hello"); // đúng về chữ ký
```

Cast argument thành `Object` tạo descriptor khớp. Không phải cứ Java cho phép `String` gán cho `Object` là `invokeExact` sẽ tự chuyển sang `Object`.

## 5. Receiver của virtual method cũng là một argument phải khớp

Với `MethodHandles.Lookup.findVirtual`, `MethodType` đưa vào khi **tra cứu** liệt kê các tham số khai báo của instance method, **không bao gồm receiver**. Nhưng handle nhận được có **receiver là tham số đầu tiên**:

```java
MethodHandle substring = MethodHandles.publicLookup().findVirtual(
        String.class, "substring",
        MethodType.methodType(String.class, int.class));
System.out.println(substring.type()); // (String,int)String
```

Dù `String.substring(int)` trong Java source trông chỉ có một tham số `int`, việc gọi handle bằng `invokeExact` đòi **hai đối số**: receiver `String`, sau đó index `int`. Cả kiểu receiver lẫn return type đều phải khớp.

### 5.1. Chương trình Java 17+ đầy đủ: receiver, `bindTo`, lỗi kiểu tĩnh

Tạo **`ReceiverExactDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;

public class ReceiverExactDemo {
    public static void main(String[] args) throws Throwable {
        MethodHandle substring = MethodHandles.publicLookup().findVirtual(
                String.class, "substring",
                MethodType.methodType(String.class, int.class));
        System.out.println("virtual.type: " + substring.type());

        String text = "method";
        String tail = (String) substring.invokeExact(text, 2);
        System.out.println("tail: " + tail);

        Object objectReceiver = text;
        try {
            String wrong = (String) substring.invokeExact(objectReceiver, 2);
            System.out.println(wrong);
        } catch (WrongMethodTypeException e) {
            System.out.println("receiver mismatch: " + e.getClass().getSimpleName());
        }

        MethodHandle bound = substring.bindTo(text);
        System.out.println("bound.type: " + bound.type());
        String result = (String) bound.invokeExact(2);
        System.out.println("bound result: " + result);
    }
}
```

Chạy:

```bash
javac --release 17 ReceiverExactDemo.java
java ReceiverExactDemo
```

Stdout đã được kiểm tra:

```text
virtual.type: (String,int)String
tail: thod
receiver mismatch: WrongMethodTypeException
bound.type: (int)String
bound result: thod
```

Giải thích:

- `substring.type()` là `(String,int)String`: receiver `String` cộng với index `int`, trả `String`.
- `String tail = (String) substring.invokeExact(text,2)` dùng receiver có static type `String`; thành công.
- `Object objectReceiver` thực tế chứa `String`, nhưng call site yêu cầu `(Object,int)String`; không khớp nên ném `WrongMethodTypeException`.
- `bindTo(text)` gắn sẵn receiver và **loại bỏ tham số đầu** khỏi kiểu của handle mới. `bound.type()` trở thành `(int)String`, nên `bound.invokeExact(2)` đúng. `bindTo` được dùng cho leading reference parameter phù hợp, không phải phương tiện tự động chèn/ép kiểu tùy ý.

**Mẹo kiểm tra:** Khi thấy `WrongMethodTypeException` trên virtual handle, hãy nhìn `handle.type()` **sau khi tạo handle và sau các bước adapter/binding**, không chỉ nhìn signature của method Java ban đầu.

## 6. Kết quả `void` và lời gọi dùng như statement

Tại call site, câu lệnh:

```java
handle.invokeExact(arg);
```

không sử dụng giá trị trả về; compiler chọn **return type `void`** cho descriptor của lời gọi. Điều đó chỉ đúng với handle có return type `void`. Nếu handle trả `int`, lời gọi trên sai kiểu, chứ JVM không tự bỏ kết quả khi dùng `invokeExact`.

Ví dụ từ chương trình đầu:

```java
// add.type() == (int,int)int
add.invokeExact(10, 20); // WrongMethodTypeException: call site muốn void

// announce.type() == (String)void
announce.invokeExact("done"); // đúng: statement và handle đều trả void
```

Nếu muốn **bỏ kết quả một cách có chủ đích**, bạn vẫn có thể gọi exact với return type gốc rồi không sử dụng giá trị của biến ở các câu lệnh sau; hoặc tạo adapter `asType` có return type `void` để bỏ kết quả theo hợp đồng adapter. Đừng sửa thành một cast `(void)`: Java không cho phép cast biểu thức sang `void`.

### 6.1. `void.class` khác `Void.class`

`MethodType.methodType(void.class, String.class)` mô tả method **không trả giá trị**. `MethodType.methodType(Void.class, String.class)` mô tả method trả **một reference type `java.lang.Void`**. Hai kiểu khác nhau; `invokeExact` không tự thay đổi `void` thành `Void` hoặc ngược lại.

Với handle trả `void`, dùng lời gọi statement nếu muốn strict exact invocation; không được giả định `Object result = (Object) handle.invokeExact(...)` sẽ tự nhận `null`.

## 7. `invoke`, `invokeExact` và `asType`: ba cơ chế khác nhau

`invokeExact` không thực hiện chuyển đổi. Nhưng Java cung cấp API khác khi chương trình thật sự cần thích nghi kiểu.

| API | Quy tắc kiểu | Khi phù hợp |
| --- | --- | --- |
| `handle.invokeExact(...)` | Call-site `MethodType` phải bằng chính xác `handle.type()` | Biết signature cụ thể, cần kiểm tra kiểu chặt và logic gọi ổn định |
| `handle.invoke(...)` | Có thể thực hiện conversion như `handle.asType(callSiteType)` khi hai kiểu tương thích | Call site dùng kiểu khác nhưng conversion được phép |
| `handle.asType(newType)` | Trả **handle mới** có `type() == newType`, thực hiện các conversion được hỗ trợ khi gọi target | Muốn chuẩn hóa/chuyển đổi rõ ràng một lần rồi gọi handle đã thích nghi |
| `handle.invokeWithArguments(...)` | Nhận đối số dưới dạng `Object...` hoặc danh sách, dùng cơ chế generic invocation/conversion | Nhiều kiểu chỉ biết động và API phải làm việc với danh sách object |

Ví dụ:

```java
// add.type() == (int,int)int
long viaInvoke = (long) add.invoke(10, 20); // hợp lệ, adapt return int -> long

MethodHandle adapted = add.asType(
        MethodType.methodType(long.class, int.class, int.class));
long viaExact = (long) adapted.invokeExact(10, 20); // exact với handle MỚI
```

Cả hai trường hợp đều có thể cho giá trị `30`. Với `invoke`, cơ chế adaptation được diễn giải **như thể** dùng `asType`, chứ API không bảo đảm mỗi lần gọi sẽ tạo object handle trung gian.

### 7.1. `asType` không sửa `handle` gốc

`MethodHandle` có `MethodType` bất biến. `asType` tạo hoặc trả về một handle có kiểu mong muốn; handle ban đầu vẫn giữ kiểu cũ:

```java
// add.type() == (int,int)int
MethodHandle adapted = add.asType(
        MethodType.methodType(long.class, int.class, int.class));

System.out.println(add.type());     // (int,int)int
System.out.println(adapted.type()); // (int,int)long
```

Phần conversion ở ví dụ là **widening từ kết quả `int` sang `long`**. Không nên nhầm ví dụ này với việc `invokeExact` tự chuyển đổi: caller khớp `(int,int)long` của **adapted handle**, không còn gọi exact trực tiếp trên `add`.

Nếu conversion không thể thực hiện theo quy tắc `asType`, API có thể ném `WrongMethodTypeException` ngay lúc tạo adapter. Với những adapter dùng reference casts, target invocation sau đó có thể ném `ClassCastException` nếu object runtime không có kiểu phù hợp. Vì vậy, adapter không phải cách vô điều kiện chấp nhận mọi đối số.

### 7.2. Khi nào dùng `invoke` thay cho `invokeExact`?

Nếu caller thực sự muốn `long` trong khi target trả `int`, có hai lựa chọn minh bạch:

- Giữ strict exact call với `(int) handle.invokeExact(...)`, rồi Java widen kết quả sau khi gọi.
- Nếu mục tiêu API yêu cầu handle trả `long`, dùng `asType` để tạo handle mới `(int,int)long`, sau đó `(long) adapted.invokeExact(...)`; hoặc dùng `(long) handle.invoke(...)` cho adaptation tại call site.

`invoke` thích hợp khi cần conversion có quy tắc. `invokeExact` thích hợp khi **cả caller và handle đã thống nhất một signature cụ thể**. Không nên đổi mọi `invokeExact` thất bại thành `invoke` như một cách im lặng bỏ qua mismatch; đôi khi mismatch chỉ ra một bug về kiểu dữ liệu.

## 8. `WrongMethodTypeException`: nhận diện đúng nguyên nhân

`java.lang.invoke.WrongMethodTypeException` là một `RuntimeException`. Nó có thể xuất hiện khi `invokeExact` thấy descriptor của call site khác handle type; cũng có thể xuất hiện từ `invoke`/`asType` khi cần conversion không hỗ trợ.

Cách debug hiệu quả là lập bảng **expected và actual**:

```text
Handle type:       (int,int)int
Caller descriptor: (int,int)long
Mismatch:                    ^^^^ return type

Handle type:       (String)String
Caller descriptor: (CharSequence)String
Mismatch:           ^^^^^^^^^^^^ argument type

Handle type:       (String,int)String
Caller descriptor: (Object,int)String
Mismatch:           ^^^^^^ receiver type
```

Thông điệp `WrongMethodTypeException` thường cho biết dạng `expected ... but found ...` nhưng **đừng phụ thuộc vào chuỗi message chính xác**: nội dung chi tiết có thể khác giữa JDK/implementation. Cách bền vững là lấy `handle.type()` và xem biểu thức Java ở dòng gọi.

### 8.1. Checklist kỹ thuật khi nhận stack trace

1. Ghi rõ `handle.type()`, ví dụ `(int,int)int`. Có bao nhiêu tham số? Có receiver ngầm đã trở thành tham số đầu không? Return type là gì?
2. Kiểm tra static type của **mỗi** argument expression. Ví dụ `2` là `int`, `2L` là `long`, `Integer` khác `int`, `Object` khác `String`.
3. Xem biểu thức `invokeExact(...)` có nằm **trực tiếp trong cast** hay đứng như statement không. Trường hợp không cast trực tiếp thường có return `Object`, statement có return `void`.
4. Xác minh handle thực tế tại **thời điểm gọi**, sau `bindTo`, `asType`, `insertArguments`, `dropArguments`, các combinator hoặc phép gán lại biến.
5. Nếu dùng virtual handle, xác định receiver type chính xác; nếu đã `bindTo`, đừng truyền lại receiver.
6. Chọn sửa bằng conversion **trước/sau** lời gọi, hoặc tạo adapter được mô tả rõ; không ẩn lỗi bằng `catch (WrongMethodTypeException ignored)`.

`handle.type()` là thông tin **runtime về handle**. Nó không tự tiết lộ descriptor mà compiler đã ghi cho call site. Để xác định vế caller, phải đọc source cùng kiểu tĩnh của biểu thức, hoặc kiểm tra bytecode nếu cần.

### 8.2. Lỗi tra handle khác lỗi invokeExact

Trong chương trình tạo handle bằng `lookup.findStatic` hay `findVirtual`:

- `NoSuchMethodException`: tên method, kind hoặc `MethodType` dùng để tìm không khớp phương thức cần lấy.
- `IllegalAccessException`: `Lookup` không có quyền truy cập target method/class trong ngữ cảnh tra cứu.
- `WrongMethodTypeException`: sau khi đã có handle, call site của `invokeExact` không khớp `handle.type()` hoặc không thể tạo adaptation được yêu cầu.
- Ngoại lệ do **target** tự ném: `invokeExact` cho phép `Throwable` từ target truyền ra trực tiếp; không mặc định bọc nó trong `InvocationTargetException` như `Method.invoke`.

Không dùng `setAccessible(true)` để chữa một `WrongMethodTypeException`. Quyền truy cập và sự tương đương giữa hai `MethodType` là **hai vấn đề độc lập**.

## 9. Signature polymorphism và vai trò của Java compiler

Tại source, `MethodHandle.invokeExact` trông gần giống một method nhận `Object...` và trả `Object`, nhưng JVM xử lý cách gọi nó đặc biệt. Đây là **signature polymorphism** theo Java Language Specification và Java Virtual Machine Specification.

Lệnh `invokevirtual` ở bytecode gắn với descriptor được xây dựng riêng cho **điểm gọi cụ thể**; Java compiler không mặc định biến đối số thành `Object` và đóng vào `Object[]` như cách hiểu thông thường về varargs API. Đồng thời compiler phải ghi return type của điểm gọi:

- `(int) h.invokeExact(1, 2)` biểu diễn return `int`.
- `(String) h.invokeExact("x")` biểu diễn return `String`.
- `h.invokeExact("x");` như statement biểu diễn return `void`.
- `Object v = h.invokeExact("x");` thường biểu diễn return `Object`; kiểu của biến bên trái **không** làm call site tự đổi thành return type của target.

Khi JVM liên kết/thực thi `invokeExact`, nó so sánh descriptor call site với `MethodType` của receiver handle. Nếu không bằng nhau, nó ném `WrongMethodTypeException`. Đây là một cơ chế runtime type check, không phải overload resolution theo class của argument object.

### 9.1. Vì sao không gọi `invokeExact` qua Core Reflection?

Không nên thử:

```java
Method m = MethodHandle.class.getMethod("invokeExact", Object[].class);
m.invoke(handle, (Object) arguments);
```

Đây là **đoạn minh họa cách làm không hợp lệ** (giả sử có biến `handle`, `arguments` và import tương ứng). Core Reflection thấy biểu diễn hình thức của signature-polymorphic method, nhưng API `MethodHandle.invokeExact` không được thiết kế để thực thi theo đường `Method.invoke` đó: đường gọi trực tiếp qua Core Reflection có thể ném `UnsupportedOperationException`.

Khi cần một API hoàn toàn động nhận danh sách `Object`, hãy xem `invokeWithArguments` hoặc thiết kế adapter/invoker có `MethodType` rõ ràng; khi biết chính xác compile-time signature, gọi `invokeExact` trực tiếp.

## 10. Bẫy trong helper generic và kiểu `Object`

Hàm helper viết như sau có vẻ linh hoạt nhưng **không thích hợp với primitive-return exact handle**:

```java
// Đoạn minh họa không độc lập:
static <T> T unsafe(MethodHandle h, int a, int b) throws Throwable {
    return (T) h.invokeExact(a, b);
}
```

Sau **type erasure**, `T` không cung cấp return type `int` cụ thể cho call site này; nó thường biểu diễn return `Object`. Nếu truyền handle `(int,int)int`, có thể gặp `WrongMethodTypeException`, dù caller phía ngoài muốn `Integer` hay `int`. Việc ép kiểu ở một **lớp gọi khác** không thể sửa descriptor được compiler tạo **bên trong helper**.

Một helper cụ thể và có hợp đồng rõ:

```java
static int callIntBinary(MethodHandle h, int a, int b) throws Throwable {
    return (int) h.invokeExact(a, b);
}
```

Helper này yêu cầu handle đúng `(int,int)int`; nó phù hợp khi chương trình kiểm soát các handle và dùng chung chữ ký. Đừng nhầm return type của helper `int` với return type mà compiler tự suy ra cho `invokeExact`: chữ `(int)` trên **lời gọi cụ thể** bảo đảm descriptor mong muốn.

Nếu cần nhận nhiều signature thực sự khác nhau, hãy biểu diễn hợp đồng bằng `MethodType`, chọn/chuẩn hóa handle thích hợp hoặc dùng API gọi động. Không tạo một generic wrapper rồi cho rằng `invokeExact` sẽ dùng `T` ở runtime để chuyển kiểu.

## 11. Tiền kiểm tra `MethodType` cho điểm gọi cố định

Khi code có một kiểu kỳ vọng nhất quán, bạn có thể kiểm tra handle ngay lúc cấu hình:

```java
static int addExact(MethodHandle handle, int a, int b)
        throws Throwable {
    MethodType expected =
            MethodType.methodType(int.class, int.class, int.class);
    if (!handle.type().equals(expected)) {
        throw new IllegalArgumentException(
                "Expected " + expected + " but handle is "
                        + handle.type());
    }
    return (int) handle.invokeExact(a, b);
}
```

Đoạn này là **method minh họa** bên trong một class có import `MethodHandle` và `MethodType`. So sánh `MethodType.equals` yêu cầu cả parameter/return types trùng nhau, và biểu thức `(int) handle.invokeExact(a,b)` có call-site `(int,int)int` tương ứng.

Ưu điểm: lỗi cấu hình được phát hiện sớm, có thông tin expected/actual rõ ràng, thay vì để một `WrongMethodTypeException` xuất hiện xa nơi đăng ký handle.

Giới hạn: precheck chỉ chứng minh handle có đúng `MethodType`; nó **không** bảo đảm target method sẽ thành công với dữ liệu cụ thể. Phép chia có thể chia cho zero, receiver có thể `null`, target có thể ném exception do nghiệp vụ hoặc I/O.

### 11.1. Không so sánh kiểu lỏng lẻo rồi gọi exact

Không đủ nếu chỉ kiểm tra `parameterCount() == 2`, hoặc `Number.class.isAssignableFrom(...)`, hoặc chỉ kiểm tra return type. Chẳng hạn `(Integer,Integer)Integer` và `(int,int)int` cùng có hai tham số nhưng là hai signatures khác nhau.

`MethodType.equals` bảo đảm đúng bằng type đã dự kiến. Nếu có conversion hợp lệ cần được hỗ trợ, hãy đưa nó thành chính sách tường minh bằng `asType` và xử lý trường hợp adaptation thất bại.

## 12. Chuyển đổi tại biên để giữ exact invocation ở lõi

Một kiến trúc hay dùng là **chuẩn hóa dữ liệu ngoài lõi**, tạo typed method handle một lần, và dùng `invokeExact` nhất quán trong đường gọi trọng tâm.

Ví dụ một source nhận `Integer` nhưng target handle nhận primitive `int`:

```java
Integer first = 10;
Integer second = 20;

// Giả sử handle.type() == (int,int)int
int result = (int) handle.invokeExact(
        first.intValue(), second.intValue());
```

Ở đây unboxing diễn ra **trước** điểm gọi. Nếu `first` hoặc `second` là `null`, `intValue()` ném `NullPointerException` tại lớp chuyển đổi; nên xác minh input và báo lỗi rõ khi cần.

Nếu handle trả `int` nhưng API bên ngoài cần `long`:

```java
long answer = (int) handle.invokeExact(10, 20);
```

Exact invocation giữ nguyên return `int`; Java widen sang `long` **sau** khi nhận kết quả. Đây thường là cách đơn giản nhất khi chuyển đổi chỉ phục vụ gán kết quả.

Nếu nhiều caller thực sự cần kết quả `long` từ cùng target, có thể tạo và cache adapter:

```java
MethodHandle toLong = handle.asType(
        MethodType.methodType(long.class, int.class, int.class));
long answer = (long) toLong.invokeExact(10, 20);
```

Các đoạn là **mã minh họa** khi có `handle` đúng kiểu và import `java.lang.invoke.*`. Không cần gọi `asType` trong mỗi request nếu signature mục tiêu không thay đổi; có thể chuẩn hóa một lần lúc khởi tạo.

### 12.1. Khi conversion thất bại

Hãy phân biệt ba loại lỗi:

- **`WrongMethodTypeException`:** kiểu call site hoặc adaptation không tương thích với handle theo quy tắc Method Handles.
- **`ClassCastException`:** một reference cast được phép về mặt ký hiệu nhưng object thực tế không có kiểu đích.
- **Ngoại lệ của target:** target được gọi rồi ném lỗi. `invokeExact` không tự bọc mọi lỗi thành `InvocationTargetException`.

Chỉ nên catch `WrongMethodTypeException` ở ranh giới cấu hình/diagnostics nếu muốn thêm expected/actual và preserve cause. Với code vận hành ổn định, mismatch thường là **bug trong hợp đồng kiểu**, không phải một trường hợp nghiệp vụ bình thường.

## 13. Lỗi phổ biến và cách sửa trực tiếp

| Lỗi | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| `long x = (long) handle.invokeExact(1,2)` trên handle trả `int` | Cast sang `long` tạo return type `long` ở call site | `long x = (int) handle.invokeExact(1,2)`, hoặc tạo handle `(int,int)long` bằng `asType` |
| `Object x = (Object) handle.invokeExact(1,2)` trên handle trả `int` | Return `Object` khác `int` | `Object x = (int) handle.invokeExact(1,2)` để boxing **sau** exact call |
| `handle.invokeExact(1,2);` với handle trả `int` | Expression statement yêu cầu `void` | Dùng return `int` đúng chỗ hoặc adapter drop return phù hợp |
| Truyền `Integer` cho handle nhận `int` | Static argument type là `Integer` | Gọi `.intValue()` trước exact call, hoặc adapter có quy tắc unboxing |
| Truyền biến `CharSequence` thực tế chứa `String` | Descriptor nhận `CharSequence`, không phải `String` | Cast/validate thành `String` trước, hoặc adapter `invoke` nếu thiết kế cho phép |
| Dùng `Object` làm receiver của virtual handle `(String,int)String` | Receiver của handle phải là `String` ở call site | Dùng biến `String` hoặc cast receiver có kiểm tra |
| Quên receiver của `findVirtual` | Returned handle có receiver ở parameter đầu | Xem `handle.type()`, truyền receiver đúng kiểu |
| Truyền receiver lần nữa sau `bindTo` | `bindTo` đã loại bỏ parameter đầu khỏi handle mới | Dùng `bound.type()` để xác định arguments còn lại |
| Chỉ kiểm tra argument, bỏ qua return | `MethodType` gồm cả kết quả | So sánh toàn bộ signature; kiểm tra cast trực tiếp |
| Generic helper `(T) h.invokeExact(...)` | `T` bị erasure, return call-site không tự biến thành kiểu cụ thể | Dùng helper có return type/cast cụ thể, hoặc invoke/adapter phù hợp |
| Đổi hết `invokeExact` sang `invoke` | Có thể che giấu bug mismatch và thay đổi conversion | Xác định chính sách conversion và chuẩn hóa tại biên |
| Catch `InvocationTargetException` như `Method.invoke` | MethodHandle target exceptions được truyền ra trực tiếp | Xử lý đúng `Throwable` của target theo hợp đồng API |

## 14. Bài tập tự kiểm tra

**Câu 1.** Handle có `type() == (int,int)int`. Dòng nào đúng?

```java
int a = (int) h.invokeExact(1, 2);
long b = (long) h.invokeExact(1, 2);
long c = (int) h.invokeExact(1, 2);
Object d = (int) h.invokeExact(1, 2);
```

**Đáp án:** `a`, `c`, `d` đúng; `b` sai vì caller có return `long` trong khi handle trả `int`. Với `c`, widening diễn ra sau exact call; với `d`, boxing diễn ra sau exact call.

**Câu 2.** `String s = (String) h.invokeExact(value)` với `h.type() == (String)String`, trong đó `CharSequence value = "ok";`. Vì sao sai dù object thực tế là `String`?

**Đáp án:** call-site parameter type là `CharSequence`, không trùng `String`; `invokeExact` kiểm tra static signature. Có thể dùng `(String) value` làm argument nếu cast hợp lệ.

**Câu 3.** `h.type() == (int)void`; muốn gọi từ Java source thì kết quả phải được xử lý thế nào?

**Đáp án:** gọi `h.invokeExact(5);` như expression statement, để return descriptor là `void`. Không sử dụng cast `(Void)` hoặc `(Object)` nếu handle trả `void`.

**Câu 4.** `findVirtual(String.class,"substring",MethodType.methodType(String.class,int.class))` tạo handle type gì?

**Đáp án:** `(String,int)String` vì receiver `String` là parameter đầu của handle trả về. Nếu `bindTo("abcdef")`, type mới là `(int)String`.

**Câu 5.** `h.type() == (int,int)int`, vì sao `h.invokeExact(1,2);` như một statement bị lỗi, nhưng `(int) h.invokeExact(1,2)` được dùng trong phép gán thì thành công?

**Đáp án:** statement tạo return `void` và mismatch; cast `(int)` yêu cầu return `int`, khớp target.

**Câu 6.** Tại sao `asType(MethodType.methodType(long.class,int.class,int.class))` có thể giải quyết nhu cầu lấy `long`, nhưng không làm `h` gốc trở thành handle trả `long`?

**Đáp án:** `asType` trả handle mới với signature mới và conversion kết quả `int` → `long`. `MethodType` của `h` gốc bất biến, vẫn là `(int,int)int`.

**Câu 7.** Nếu `lookup.findStatic(...)` báo `NoSuchMethodException`, nên sửa `invokeExact` trước hay kiểm tra bước nào?

**Đáp án:** cần kiểm tra tên method, method kind, `MethodType` dùng trong lookup và declaring class. Chưa có handle hợp lệ để gọi, nên đây không phải lỗi type mismatch tại `invokeExact`.

**Câu 8.** Một target `int compute(int)` ném `IllegalStateException` bên trong body khi được gọi bằng `invokeExact` với signature đúng. Ngoại lệ có mặc định trở thành `InvocationTargetException` không?

**Đáp án:** không. Method handle invocation truyền exception do target ném ra trực tiếp. `InvocationTargetException` là wrapper thường gặp ở Core Reflection `Method.invoke`/`Constructor.newInstance`; hai cơ chế không nên bị đánh đồng.

**Câu 9.** Một helper generic trả `T` viết `return (T) h.invokeExact(1,2);` nhưng target trả `int`. Vì sao caller có `Integer value = helper(...)` không sửa được mismatch?

**Đáp án:** descriptor của `invokeExact` được tạo tại **call site bên trong helper**, nơi `T` bị erasure và không xác định return `int`. Cast ở tầng caller khác không sửa được bytecode descriptor đó. Cần helper có kiểu `int` cụ thể hoặc cơ chế gọi động/adaptation thích hợp.

## 15. Tài liệu chuẩn

- **Java SE 21 — `MethodHandle` API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandle.html — định nghĩa `invokeExact`, `invoke`, `asType`, cơ chế call-site descriptor, exact matching và `WrongMethodTypeException`.
- **Java SE 21 — `MethodType` API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodType.html — cấu trúc danh sách parameter và return type.
- **Java SE 21 — `MethodHandles.Lookup` API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html — `findStatic`, `findVirtual` và quyền lookup.
- **Java SE 21 — `WrongMethodTypeException` API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/WrongMethodTypeException.html — ngoại lệ khi call site hoặc adaptation không tương thích.
- **Java Language Specification 21, §15.12:** https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.12 — chữ ký polymorphic và cách xác định kiểu parameter/return tại Java source.
- **Java Virtual Machine Specification 21, §6.5 `invokevirtual`:** https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-6.html#jvms-6.5.invokevirtual — type equality khi `invokeExact` thực thi.

> **Ghi nhớ:** Với `invokeExact`, phải đọc `handle.type()` **từ trái sang phải và bao gồm cả kiểu kết quả**. Khi caller khác handle về bất kỳ một kiểu tĩnh nào, JVM không tự conversion; hãy sửa biểu thức caller hoặc tạo adapter có `MethodType` rõ ràng.