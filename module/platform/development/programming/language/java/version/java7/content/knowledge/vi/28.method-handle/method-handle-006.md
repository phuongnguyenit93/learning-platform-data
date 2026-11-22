# Java 7 — MethodHandle: Phân biệt invokeExact với invoke

## 1. Vì sao cần phân biệt hai cách gọi?

`java.lang.invoke.MethodHandle` là tham chiếu có kiểu tới một thao tác có thể thực thi như static method, instance method, constructor, getter/setter hoặc một tổ hợp thao tác. API có từ Java 7 và **vẫn hiện hành trong Java 17+**. Bản thân MethodHandle có kiểu chính xác được biểu diễn bằng `MethodType`, ví dụ `(int,int)int`: nhận hai `int` và trả một `int`.

Hai invokers được sử dụng nhiều nhất:

- **`invokeExact(...)`:** Call site phải khớp **chính xác** với `handle.type()`: số lượng, thứ tự và kiểu tĩnh của mọi đối số, kể cả receiver; đồng thời kiểu **giá trị trả về** phải giống hệt. Không boxing/unboxing/widening/ref-cast chỉ để sửa type mismatch.
- **`invoke(...)`:** Nếu call site đã khớp thì xử lý như `invokeExact`. Nếu khác, JVM thử điều chỉnh kiểu theo những chuyển đổi hợp lệ, tương đương `handle.asType(callSiteType)`. Có thể boxing, unboxing, primitive widening, reference casting và chuyển kiểu trả về; không phải mọi phép ép kiểu đều được chấp nhận.

Khi `invokeExact` gặp mismatch hoặc `invoke` không thể thiết lập chuyển đổi, lỗi thường là `WrongMethodTypeException`. Nếu `invoke` tạo được adapter nhưng object thực tế không thể cast/unbox, có thể xảy ra `ClassCastException` hoặc `NullPointerException`.

**Khác biệt quan trọng nhất:** Kiểu trả về **tại call site** cũng là thành phần của chữ ký được kiểm tra. Hai biểu thức gọi cùng một handle và truyền cùng arguments vẫn có thể có kết quả khác nhau chỉ vì phép cast bao quanh khác nhau.

```java
int exact = (int) handle.invokeExact(3, 4);    // OK nếu type (int,int)int.
long wrong = (long) handle.invokeExact(3, 4); // Sai kiểu trả về: WMT.
long flexible = (long) handle.invoke(3, 4);   // Có thể đổi int -> long.
```

Đây là snippet trong phương thức với `MethodHandle handle` có type `(int,int)int` và method khai báo `throws Throwable`. Chữ `WMT` trong comment là viết tắt `WrongMethodTypeException`; dòng thứ hai **cố ý sai ở runtime**, dù có thể biên dịch.

## 2. Từ MethodHandles.Lookup tới MethodType

Một ví dụ chuẩn:

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();
MethodHandle handle = lookup.findStatic(
        Example.class, "add",
        MethodType.methodType(int.class, int.class, int.class));
```

Đây là snippet, yêu cầu class `Example` có static method `int add(int,int)`. Import:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
```

`MethodType.methodType(returnType, parameterTypes...)` nhận **return type trước**, không phải ba tham số int. Handle được tạo ở ví dụ có:

```text
handle.type() = (int,int)int
returnType    = int
parameter[0]  = int
parameter[1]  = int
```

Đối với lời gọi `invokeExact`, **toàn bộ** descriptor này phải trùng descriptor mà Java compiler phát sinh cho điểm gọi. Không đủ nếu chỉ nói “tham số 3 và 4 đều là int”.

### 2.1. MethodHandle có kiểu; tên phương thức không quyết định kiểu cuối cùng

Sau khi tạo handle, bạn có thể gọi `asType`, `bindTo`, `insertArguments` hoặc combinators khác để có **handle mới** với MethodType khác. Khi gọi exact, phải dùng **`type()` của handle hiện tại**, không nhất thiết dùng chữ ký method gốc.

### 2.2. Lookup cũng có thể thất bại trước khi invoke

`findStatic`/`findVirtual` có thể ném `NoSuchMethodException` hoặc `IllegalAccessException` khi method signature không khớp hoặc lookup thiếu quyền. Đây là lỗi **giai đoạn tạo handle**, khác với `WrongMethodTypeException` ở giai đoạn gọi.

### 2.3. MethodHandle có phải reflection không?

MethodHandle thuộc package `java.lang.invoke`, thường được dùng ở runtime, framework và dynamic language support. Tuy có công dụng liên quan reflection, nó **không** giống `java.lang.reflect.Method.invoke` về liên kết, tham số, ngoại lệ và cách JVM gọi. MethodHandle có type cụ thể và các quy tắc signature-polymorphic riêng.

## 3. Vì sao compiler xác định return type theo cast?

Hai phương thức `MethodHandle.invokeExact` và `MethodHandle.invoke` thuộc nhóm **signature-polymorphic invokers**. Trong Java source, bạn có thể viết các lời gọi với danh sách tham số và kiểu kết quả khác nhau; compiler tạo *symbolic method descriptor* cụ thể cho từng call site.

Javadoc Java SE 17 mô tả cách xác định return type:

1. **Có cast trực tiếp trên lời gọi**, ví dụ `(int)handle.invokeExact(...)` → return type call site là `int`.
2. **Là biểu thức nhưng không cast**, ví dụ `Object result = handle.invokeExact(...)` → return type call site là `Object`.
3. **Là statement không dùng kết quả**, ví dụ `handle.invokeExact(...)` → return type call site là `void`.
4. Argument types được lấy từ **kiểu tĩnh của các biểu thức argument**, không tự chuyển đổi theo quy tắc gọi method thông thường.
5. Literal `null` không ép kiểu là một góc cạnh đặc biệt: compiler có thể ghi descriptor argument là `Void`. Muốn exact với tham số String, nên viết `(String)null`.

Giả sử `handle.type() == (int,int)int`:

```text
Source                                         Call-site descriptor    Kết quả
(int) handle.invokeExact(3, 4)               (int,int)int           OK
(long) handle.invokeExact(3, 4)              (int,int)long          WMT
Object x = handle.invokeExact(3, 4)          (int,int)Object        WMT
handle.invokeExact(3, 4)                     (int,int)void          WMT
(long) handle.invoke(3, 4)                   (int,int)long          OK, widen result
Object x = handle.invoke(3, 4)               (int,int)Object        OK, box result
```

**WMT** = `WrongMethodTypeException`. Bảng diễn giải trường hợp handle gốc là static method không phải varargs collector, không có tác dụng phụ quan trọng.

### 3.1. Tại sao String có thể gán sang Object bình thường, nhưng exact lại sai?

Trong Java thông thường, một `String` có thể gán sang `Object`. Với lời gọi signature-polymorphic, cú pháp:

```java
Object value = stringHandle.invokeExact("hello");
```

làm call site mang return descriptor `Object`, trong khi `stringHandle.type()` có thể là `(String)String`. Đây là **mismatch của MethodType**, không phải Java assignment compatibility thông thường. Cách chính xác:

```java
String value = (String) stringHandle.invokeExact("hello");
```

hoặc nếu muốn Object:

```java
Object value = stringHandle.invoke("hello");
```

Trong trường hợp thứ ba, `invoke` có thể chuyển String result thành Object.

### 3.2. Khi gọi không dùng result

```java
int x = (int) handle.invokeExact(3, 4); // exact nếu return int.
handle.invokeExact(3, 4);               // mismatch vì call site muốn void.
handle.invoke(3, 4);                    // có thể bỏ kết quả qua adaptation.
```

Một handle thực sự trả `void`, như tới `PrintStream.println(String)`, có thể được gọi bằng `invokeExact` như statement nếu arguments và receiver cũng khớp.

## 4. So sánh chính xác từng loại chuyển đổi

| Call site so với target `(int,int)int` | `invokeExact` | `invoke` | Lý do |
| --- | --- | --- | --- |
| `(int,int)int` | OK | OK | Descriptor khớp hoàn toàn |
| `(int,int)long` | WMT | OK | int → long result widening |
| `(Integer,Integer)int` | WMT | OK | Unboxing sang int |
| `(Object,Object)Object`, hai Objects chứa Integer | WMT | OK | Cast/unbox arguments, box result |
| `(long,int)int` | WMT | WMT | Narrowing long → int không được asType ngầm cho phép |
| `(Object,int)int`, Object thực là String | WMT | ClassCastException | Adapter tạo được nhưng cast/unbox runtime thất bại |
| `(int,int)void` | WMT | OK | Return có thể bị bỏ qua |
| `(int)int` | WMT | WMT | Sai arity đối với fixed-arity handle |
| `(int,int)String` | WMT | WMT | Không chuyển int result thành String theo asType |

Không xem bảng trên như cam kết tất cả `Throwable` từ target đều bị bắt. Các ngoại lệ do **phương thức đích** ném vẫn được truyền ra.

### 4.1. invoke cho phép gì?

Một số conversion theo quy tắc `asType`:

- **Primitive widening**: `byte→int`, `int→long`, `float→double`.
- **Boxing**: target trả int, call site cần Object.
- **Unboxing**: target cần int, call site có Integer hoặc Object chứa wrapper tương thích.
- **Reference cast**: call site cung cấp Object, target cần String; việc cast được kiểm tra khi chạy.
- **Drop result**: target trả giá trị nhưng call site muốn void.

### 4.2. invoke không tự làm gì?

- Không tự ép hẹp `long→int` như một implicit conversion theo asType.
- Không parse `"42"` thành int.
- Không tự thêm hoặc loại arguments cho handle fixed arity.
- Không làm StringBuilder trở thành String chỉ vì cả hai cùng implements CharSequence.
- Không chặn ngoại lệ do target ném.
- Không thay đổi MethodType của original handle tại chỗ.

Khi muốn chuyển kiểu **hẹp** có chủ ý, xem `MethodHandles.explicitCastArguments` và kiểm soát khả năng mất dữ liệu.

## 5. Chương trình hoàn chỉnh 1: ExactVersusInvokeDemo

Chương trình Java 17+ lấy handle cho `static int add(int,int)`. Các lỗi được catch để tất cả stdout có kết quả xác định.

**Tệp `ExactVersusInvokeDemo.java`:**

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;

public class ExactVersusInvokeDemo {
    public static int add(int a, int b) { return a + b; }

    public static void main(String[] args) throws Throwable {
        MethodHandle mh = MethodHandles.lookup().findStatic(
                ExactVersusInvokeDemo.class, "add",
                MethodType.methodType(int.class, int.class, int.class));

        int exact = (int) mh.invokeExact(3, 4);
        int flexible = (int) mh.invoke(3, 4);
        long widened = (long) mh.invoke(3, 4);
        int unboxed = (int) mh.invoke(
                Integer.valueOf(3), Integer.valueOf(4));
        Object boxed = mh.invoke(3, 4);

        boolean exactReturnMismatch = false;
        try {
            long ignored = (long) mh.invokeExact(3, 4);
        } catch (WrongMethodTypeException expected) {
            exactReturnMismatch = true;
        }

        boolean exactArgumentMismatch = false;
        try {
            int ignored = (int) mh.invokeExact(Integer.valueOf(3), 4);
        } catch (WrongMethodTypeException expected) {
            exactArgumentMismatch = true;
        }

        boolean narrowingRejected = false;
        try {
            int ignored = (int) mh.invoke(3L, 4);
        } catch (WrongMethodTypeException expected) {
            narrowingRejected = true;
        }

        boolean wrongReferenceRejected = false;
        try {
            int ignored = (int) mh.invoke((Object) "bad", 4);
        } catch (ClassCastException expected) {
            wrongReferenceRejected = true;
        }

        System.out.println("type = " + mh.type());
        System.out.println("invokeExact int = " + exact);
        System.out.println("invoke int = " + flexible);
        System.out.println("invoke long result = " + widened);
        System.out.println("invoke boxed arguments = " + unboxed);
        System.out.println("invoke Object result = " + boxed);
        System.out.println("exact return mismatch = " + exactReturnMismatch);
        System.out.println("exact argument mismatch = " + exactArgumentMismatch);
        System.out.println("invoke rejects narrowing long->int = " +
                narrowingRejected);
        System.out.println("invoke bad reference cast = " +
                wrongReferenceRejected);
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 ExactVersusInvokeDemo.java
java ExactVersusInvokeDemo
```

**Stdout đã xác minh trên Windows/JDK 24, tương thích Java 17:**

```text
type = (int,int)int
invokeExact int = 7
invoke int = 7
invoke long result = 7
invoke boxed arguments = 7
invoke Object result = 7
exact return mismatch = true
exact argument mismatch = true
invoke rejects narrowing long->int = true
invoke bad reference cast = true
```

### 5.1. Vì sao exact với Integer sai?

`Integer.valueOf(3)` là biểu thức có static type `Integer`, trong khi target cần `int`. `invokeExact` không tự unbox. `invoke` có thể unbox và gọi target.

### 5.2. Vì sao invoke với long kết quả đúng, nhưng long argument sai?

Ở `(long) mh.invoke(3,4)`, target trả int, call site muốn long: đó là **widening**, phù hợp.

Ở `(int) mh.invoke(3L,4)`, call site cung cấp long cho target muốn int: đó là **narrowing**, không phải implicit asType conversion.

### 5.3. Vì sao Object "bad" ném ClassCastException?

Call site có type Object, nên JVM có thể xây adapter Object→int. Khi runtime object thực tế là String, nó không thể unbox thành int, vì vậy lỗi value cast/unboxing, không phải lỗi không thể định nghĩa adapter.

## 6. Receiver trong findVirtual: đừng quên đối số ẩn

Với `String.substring(int,int)`, ta tìm virtual method:

```java
MethodHandle mh = MethodHandles.lookup().findVirtual(
        String.class, "substring",
        MethodType.methodType(String.class, int.class, int.class));
```

`MethodType` yêu cầu khi **lookup** là `(int,int)String`, vì nó mô tả chữ ký method `substring`. Nhưng type của **handle nhận được** là:

```text
(String,int,int)String
 ^^^^^^
 receiver đứng ở vị trí đối số thứ nhất
```

Lời gọi exact phải truyền String receiver, int start, int end và cast return String:

```java
String value = (String) mh.invokeExact("world", 1, 4);
```

### 6.1. Static type quan trọng hơn runtime class với exact

Nếu có:

```java
CharSequence cs = "world";
String value = (String) mh.invokeExact(cs, 1, 4);
```

thì receiver static type là `CharSequence`, không phải String: exact ném `WrongMethodTypeException` dù object thực là String.

Có thể đổi thành:

```java
String value = (String) mh.invoke((Object) cs, 1, 4);
```

nếu runtime object thực sự là String. Với một StringBuilder, cast sang String thất bại.

### 6.2. Chương trình hoàn chỉnh 2: VirtualHandleDemo

**Tệp `VirtualHandleDemo.java`:**

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;

public class VirtualHandleDemo {
    public static void main(String[] args) throws Throwable {
        MethodHandle substring = MethodHandles.lookup().findVirtual(
                String.class, "substring",
                MethodType.methodType(String.class, int.class, int.class));

        String exact = (String) substring.invokeExact("world", 1, 4);
        String adapted = (String) substring.invoke(
                (Object) "world", Integer.valueOf(1), Integer.valueOf(4));
        Object resultAsObject = substring.invoke("world", 1, 4);

        boolean receiverMismatch = false;
        try {
            String ignored = (String) substring.invokeExact(
                    (CharSequence) "world", 1, 4);
        } catch (WrongMethodTypeException expected) {
            receiverMismatch = true;
        }

        boolean wrongReceiver = false;
        try {
            String ignored = (String) substring.invoke(
                    (Object) new StringBuilder("abc"), 0, 1);
        } catch (ClassCastException expected) {
            wrongReceiver = true;
        }

        MethodHandle bound = substring.bindTo("world");
        String boundResult = (String) bound.invokeExact(1, 4);

        System.out.println("virtual type = " + substring.type());
        System.out.println("exact substring = " + exact);
        System.out.println("adapted substring = " + adapted);
        System.out.println("invoke Object return = " + resultAsObject);
        System.out.println("exact receiver mismatch = " + receiverMismatch);
        System.out.println("invoke wrong receiver = " + wrongReceiver);
        System.out.println("bound type = " + bound.type());
        System.out.println("bound exact result = " + boundResult);
    }
}
```

Chạy:

```bash
javac --release 17 VirtualHandleDemo.java
java VirtualHandleDemo
```

**Stdout đã xác minh:**

```text
virtual type = (String,int,int)String
exact substring = orl
adapted substring = orl
invoke Object return = orl
exact receiver mismatch = true
invoke wrong receiver = true
bound type = (int,int)String
bound exact result = orl
```

### 6.3. bindTo thay đổi type và số lượng arguments

`substring.bindTo("world")` cố định receiver, nên type của handle mới từ `(String,int,int)String` thành `(int,int)String`. Từ đó:

```java
String text = (String) bound.invokeExact(1, 4);
```

là exact đúng. Nếu vẫn truyền thêm receiver vào bound handle, sẽ sai arity.

`bindTo` gắn một reference argument ở đầu handle. Để cố định primitive argument ở vị trí bất kỳ, cân nhắc `MethodHandles.insertArguments`.

## 7. asType: adapter có chữ ký chính xác mới

Giả sử original handle có type `(int,int)int` nhưng caller cần result long. Có thể xây adapter một lần:

```java
MethodHandle longReturn = original.asType(
        MethodType.methodType(long.class, int.class, int.class));
long value = (long) longReturn.invokeExact(4, 9);
```

Đây là snippet khi original target là method nhận hai int và trả int. `longReturn.type() == (int,int)long`, nên `invokeExact` **khớp với adapter**. Adapter sẽ widen kết quả int của target sang long.

```text
Caller:           (int,int)long
                       |
                   invokeExact
                       |
Adapter:          (int,int)long
                       |
                call target + widen
                       |
Original:         (int,int)int
```

**Quan trọng:** `asType` không biến `invokeExact` thành `invoke`. Nó tạo **một handle mới mang type khác**. `invokeExact` vẫn yêu cầu khớp 100% với type của handle mà nó được gọi trên.

### 7.1. asType có cho narrowing không?

Không phải mọi conversion đều hợp lệ. Nếu cần long→int ở argument, `asType` theo quy tắc bình thường từ chối và có thể ném `WrongMethodTypeException`. Đừng sử dụng `invoke` hoặc `asType` như một cơ chế tự động cắt bớt giá trị.

### 7.2. Khi cần explicit narrowing

`MethodHandles.explicitCastArguments(target,newType)` có thể tạo adapter dùng explicit narrowing; cần kiểm tra miền giá trị vì long→int có thể mất dữ liệu. Ví dụ:

```java
MethodHandle explicit = MethodHandles.explicitCastArguments(
        maxHandle, MethodType.methodType(int.class, long.class, long.class));
int result = (int) explicit.invokeExact(4L, 9L);
```

Đây là snippet với `maxHandle.type() == (int,int)int`. Result là 9, nhưng với các long vượt giới hạn int, semantics cast có thể làm giá trị thay đổi. Chỉ dùng nếu requirement thật sự cho phép narrowing.

### 7.3. insertArguments cố định các đối số

```java
MethodHandle bound = MethodHandles.insertArguments(maxHandle, 0, 10);
int result = (int) bound.invokeExact(9);
```

Original có type `(int,int)int`, còn `bound.type()` là `(int)int`. Nếu target thực hiện max(10,9), kết quả 10. Sau khi biến đổi handle, luôn đọc `bound.type()` để biết chữ ký exact mới.

## 8. Chương trình hoàn chỉnh 3: TypeAdapterDemo

**Tệp `TypeAdapterDemo.java`:**

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;

public class TypeAdapterDemo {
    public static int max(int a, int b) { return Math.max(a, b); }

    public static void main(String[] args) throws Throwable {
        MethodHandle mh = MethodHandles.lookup().findStatic(
                TypeAdapterDemo.class, "max",
                MethodType.methodType(int.class, int.class, int.class));

        MethodHandle widenedReturn = mh.asType(
                MethodType.methodType(long.class, int.class, int.class));
        long adaptedExact = (long) widenedReturn.invokeExact(4, 9);
        int originalExact = (int) mh.invokeExact(4, 9);
        long plainInvoke = (long) mh.invoke(4, 9);

        boolean implicitNarrowingRejected = false;
        try {
            int ignored = (int) mh.invoke(4L, 9L);
        } catch (WrongMethodTypeException expected) {
            implicitNarrowingRejected = true;
        }

        MethodHandle explicitNarrow = MethodHandles.explicitCastArguments(
                mh, MethodType.methodType(int.class, long.class, long.class));
        int explicitValue = (int) explicitNarrow.invokeExact(4L, 9L);

        MethodHandle boundFirst = MethodHandles.insertArguments(mh, 0, 10);
        int boundValue = (int) boundFirst.invokeExact(9);

        MethodHandle boxedAdapter = mh.asType(
                MethodType.methodType(Object.class, Object.class, Object.class));
        Object result = (Object) boxedAdapter.invokeExact(
                (Object) Integer.valueOf(4), (Object) Integer.valueOf(9));
        Object varargs = mh.invokeWithArguments(4, 9);

        System.out.println("original type = " + mh.type());
        System.out.println("adapted type = " + widenedReturn.type());
        System.out.println("original exact = " + originalExact);
        System.out.println("widened invoke = " + plainInvoke);
        System.out.println("adapted exact long = " + adaptedExact);
        System.out.println("implicit narrowing rejected = " +
                implicitNarrowingRejected);
        System.out.println("explicit cast result = " + explicitValue);
        System.out.println("bound first argument = " + boundValue);
        System.out.println("boxed adapter result = " + result);
        System.out.println("invokeWithArguments result = " + varargs);
    }
}
```

Chạy:

```bash
javac --release 17 TypeAdapterDemo.java
java TypeAdapterDemo
```

**Stdout đã xác minh:**

```text
original type = (int,int)int
adapted type = (int,int)long
original exact = 9
widened invoke = 9
adapted exact long = 9
implicit narrowing rejected = true
explicit cast result = 9
bound first argument = 10
boxed adapter result = 9
invokeWithArguments result = 9
```

### 8.1. Bốn thay đổi trong ví dụ

1. `asType` tạo adapted handle `(int,int)long` mà không sửa original.
2. `explicitCastArguments` cho phép long arguments được cast về int.
3. `insertArguments` rút arity từ hai int xuống một int.
4. `asType((Object,Object)Object)` tạo một handle mà exact phải truyền **hai Object và nhận Object**.

Cụ thể, khi adapter yêu cầu Object, phải viết `(Object) Integer.valueOf(4)`; chỉ truyền `Integer.valueOf(4)` có static type Integer, khác Object, và exact vẫn sai.

### 8.2. invokeWithArguments khác invoke

`invokeWithArguments(Object...)` là tiện ích cho danh sách arguments ở runtime, chuyển đổi từ các Object rồi trả Object. Nó không yêu cầu một call site có typed signature giống invokeExact, nhưng vẫn có thể throw khi số đối số hoặc conversion không hợp lệ. Không chọn nó trong hot loop chỉ để tránh suy nghĩ về MethodType nếu một typed invocation đã đủ rõ ràng.

## 9. Chương trình hoàn chỉnh 4: return type và statement context

**Tệp `CallSiteReturnDemo.java`:**

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.WrongMethodTypeException;

public class CallSiteReturnDemo {
    public static void main(String[] args) throws Throwable {
        MethodHandle identity = MethodHandles.identity(String.class);
        String exact = (String) identity.invokeExact("hello");
        Object adaptedReturn = identity.invoke("hello");

        boolean wrongReturn = false;
        try {
            Object ignored = identity.invokeExact("hello");
        } catch (WrongMethodTypeException expected) {
            wrongReturn = true;
        }

        boolean statementRequiresVoid = false;
        try {
            identity.invokeExact("hello");
        } catch (WrongMethodTypeException expected) {
            statementRequiresVoid = true;
        }

        String nullExact = (String) identity.invokeExact((String) null);

        System.out.println("type = " + identity.type());
        System.out.println("exact = " + exact);
        System.out.println("invoke Object return = " + adaptedReturn);
        System.out.println("exact Object return fails = " + wrongReturn);
        System.out.println("exact statement fails = " + statementRequiresVoid);
        System.out.println("typed null exact = " + (nullExact == null));
    }
}
```

Chạy:

```bash
javac --release 17 CallSiteReturnDemo.java
java CallSiteReturnDemo
```

**Stdout đã xác minh:**

```text
type = (String)String
exact = hello
invoke Object return = hello
exact Object return fails = true
exact statement fails = true
typed null exact = true
```

### 9.1. Vì sao exact Object return fails?

Handle identity có type `(String)String`. Lệnh `Object ignored = identity.invokeExact("hello")` có call-site type `(String)Object`, không khớp return String. `invoke` lại có thể nâng String result lên Object.

### 9.2. Vì sao exact statement fails?

Một lời gọi không dùng kết quả có return descriptor `void`. Nếu target thực tế trả String, exact thất bại. Với plain `invoke`, adapter có thể bỏ kết quả. Nếu handle trả void thật, exact statement vẫn hoàn toàn hợp lệ khi arguments khớp.

### 9.3. Tại sao phải cast null?

`(String) identity.invokeExact((String)null)` bảo đảm static type String ở argument và return. Nếu literal null không cast, compiler có thể dùng descriptor khác, khiến exact mismatch dù giá trị runtime null gán được cho mọi reference.

## 10. Exception: phân loại lỗi chính xác

| Exception | Thường xảy ra khi | Nên xử lý |
| --- | --- | --- |
| `WrongMethodTypeException` | Exact type mismatch hoặc invoke/asType adaptation không thực hiện được | So `handle.type()` và call-site signature |
| `ClassCastException` | Adaptation reference được cho phép nhưng object runtime sai kiểu | Validate/cast input trước khi invoke |
| `NullPointerException` | Thí dụ unboxing null thành primitive | Kiểm tra null và contract |
| `NoSuchMethodException` | `Lookup.findXxx` không tìm thấy đúng method descriptor | Sửa lookup signature/name |
| `IllegalAccessException` | Lookup thiếu quyền truy cập method/field | Tuân thủ access/module rules |
| Ngoại lệ từ target | Business method tự ném, như `ArithmeticException` | Xử lý theo nghiệp vụ, không quy cho MethodType |

`invokeExact` và `invoke` khai báo `throws Throwable` vì handle có thể gọi tới target ném bất kỳ Throwable nào. Trong demos có `main(String[] args) throws Throwable`. Trong production, thiết kế boundary exceptions có chủ đích thay vì catch `Throwable` và bỏ qua.

### 10.1. Case narrowing: lỗi cấu hình, không phải lỗi dữ liệu ngẫu nhiên

Nếu handle cần int nhưng caller truyền long, `invoke` không tự narrow. Sửa tốt nhất là **thống nhất API dùng int** khi đầu vào thực tế là int. Nếu caller thật sự quản lý long và nghiệp vụ cho phép thu hẹp, validate rồi tạo adapter `explicitCastArguments` có chủ đích.

### 10.2. ClassCastException là giai đoạn khác

Nếu caller đưa `(Object)"bad"` tới target cần int, JVM có thể tạo adapter Object→int về mặt descriptor. Khi chạy, String không thể unbox thành int nên ném ClassCastException. Điều này khác trường hợp `long→int` bị từ chối ngay bởi quy tắc chuyển type của adapter.

### 10.3. Không nuốt mọi lỗi

Anti-pattern:

```java
try {
    mh.invokeExact(x, y);
} catch (Throwable ignored) {
    // Sai: có thể bỏ qua lỗi MethodType hoặc lỗi thật trong target.
}
```

Đây là snippet cố ý sai về error handling. Hãy kiểm tra MethodType, sửa caller hoặc expose một exception rõ ràng. Không để lỗi type bị thay bằng kết quả null khiến phần còn lại của chương trình hiểu sai.

## 11. Reflection, invoker factories và convenience APIs

`java.lang.reflect.Method.invoke` khác với `MethodHandle.invoke`. Khi dùng reflection để gọi trực tiếp method placeholder mang tên `MethodHandle.invokeExact` trên đối tượng MethodHandle, đó **không phải** signature-polymorphic invocation và theo Javadoc Java 17 sẽ ném `UnsupportedOperationException`.

Nếu thực sự cần một **MethodHandle đại diện cho invoker có type cụ thể**, API `MethodHandles.exactInvoker(type)` và `MethodHandles.invoker(type)` phục vụ bài toán này. Đây là kỹ thuật nâng cao trong framework/bytecode generation, không cần dùng để gọi một handle đơn giản trong code ứng dụng.

### 11.1. invokeWithArguments phù hợp khi nào?

- Bộ arguments được lưu trong `Object[]` hoặc được tạo lúc runtime.
- Code bridge/framework muốn gọi handle có signature dynamic.
- Test tools thử nhiều combinations của inputs.
- Người viết chấp nhận boxing, kiểm tra kiểu runtime và chi phí bổ sung khi cần.

Nhưng không xem invokeWithArguments là API “không có kiểu”. Nó vẫn có validation, exception semantics và variable arity rules.

### 11.2. Varargs collector có quy tắc đặc biệt

Nếu `mh.isVarargsCollector() == true`, `invoke` có thể tự gom các trailing arguments theo quy tắc collector. Trái lại, với fixed-arity handle, số arguments sai thường dẫn tới WrongMethodTypeException. Trong bài, các demo dùng các handles fixed arity; không trộn lẫn varargs behavior vào kết luận cơ bản.

## 12. Lookup, static/virtual/constructor và field handles

### 12.1. Static method

`findStatic` tạo handle với parameters của static method, không có receiver. Ví dụ `static int add(int,int)` cho type `(int,int)int`.

### 12.2. Virtual method

`findVirtual` tạo handle với receiver đầu tiên. Ví dụ `String.substring(int,int)` cho type `(String,int,int)String`.

### 12.3. Constructor

`findConstructor` khi tìm constructor có những quy tắc type riêng; handle được tạo thường trả instance class. Kiểm tra `handle.type()` **sau lookup** trước khi exact invoke, không tự suy rằng constructor handle trả void chỉ vì constructor không có kiểu trả về trong cú pháp Java.

### 12.4. Field getter/setter

Getter thường trả giá trị field, setter trả void; instance field handles có receiver, static field handles không có receiver. Các APIs `Lookup.findGetter/findSetter/findStaticGetter/findStaticSetter` có chữ ký khác nhau, nhưng vẫn tuân thủ quy tắc exact/invoke theo MethodType.

### 12.5. MethodHandles combinators

`asType`, `bindTo`, `insertArguments`, `dropArguments`, `filterArguments`, `permuteArguments`, `asCollector`, `asSpreader` thay đổi hoặc điều phối arguments/results. Sau mỗi bước, có thể in `type()` của handle mới để kiểm tra. Không assume type của handle ban đầu vẫn được giữ nguyên.

## 13. Mẫu debug WrongMethodTypeException

Trình tự hữu ích:

1. **In `mh.type()`**.
2. Xác nhận handle có phải fixed arity/varargs collector.
3. Xem dùng `invokeExact` hay `invoke`.
4. Đếm arguments, kể cả receiver của virtual handle.
5. Kiểm tra static type từng argument, không chỉ runtime class.
6. Kiểm tra cast trực tiếp trên kết quả.
7. Nếu lời gọi là statement, kiểm tra return descriptor void.
8. Nếu gọi trên adapter, xem **adapter.type()**, không type original.
9. Nếu dùng invoke, phân loại chuyển đổi tương thích asType không.
10. Nếu type có thể thích ứng nhưng object cast thất bại, xử lý `ClassCastException`/null.
11. Nếu cần narrowing, kiểm tra business range rồi chọn explicit adapter.
12. Nếu lỗi ở lookup, phân biệt `NoSuchMethodException`/`IllegalAccessException`.
13. Sau khi sửa, chạy demo/unit tests kiểm tra cả success và failure cases.

### 13.1. Một ví dụ debug nhanh

```text
Handle.type(): (String,int,int)String
Call site:     (CharSequence,int,int)String
Invoker:       invokeExact
Lỗi:           WrongMethodTypeException

Giải pháp 1: dùng receiver static String rồi exact.
Giải pháp 2: dùng invoke nếu thật sự chấp nhận cast khi runtime.
Giải pháp 3: tạo asType adapter có type mong muốn,
             sau đó invokeExact đúng descriptor adapter.
```

Giải pháp 1 phù hợp khi code đã biết receiver là String. Giải pháp 2 mở ra khả năng runtime ClassCastException nếu receiver không phải String. Giải pháp 3 hữu ích trong một framework có API signature được chuẩn hóa.

### 13.2. Không suy từ cách in value

`Integer.valueOf(3)` và primitive `3` đều in là 3, nhưng static types khác nhau. Một kết quả `int 7` và `long 7L` cũng có display giống nhau; điều đó **không** làm descriptor giống nhau. Inspect source static types/casts.

### 13.3. Kiểm tra ClassLoader

Các reference types trong MethodType là `Class<?>` objects. Hai class cùng tên nhưng do hai class loaders khác nhau nạp có thể là hai kiểu khác nhau. Khi debug framework/plugin runtime, đừng chỉ so chuỗi tên; type matching thực sự dùng resolved Class identity.

## 14. Thread safety và performance

MethodHandle có tính **immutable**, nên object handle sau khi xây dựng có thể được chia sẻ. Nhưng một handle có thể gọi target sửa một `HashMap` mutable không được đồng bộ hoặc receiver đang có state. **MethodHandle immutable không tự làm target method thread-safe.**

Về hiệu năng:

- `invokeExact` gọi với descriptor chính xác.
- `invoke` khi descriptor chính xác có hành vi như exact.
- `invoke` khi descriptor khác có thể cần adaptation; JVM có thể tối ưu.
- `asType` tạo adapter typed để nhiều call sites dùng lại khi hợp lý.
- `invokeWithArguments` tiện cho dynamic use, nhưng có thể có chi phí boxing/array/adapter.
- Lợi ích về tốc độ phụ thuộc JIT, stable call sites, method inlining, target complexity và workload.

**Không** tuyên bố `invokeExact` nhanh hơn `invoke` một tỷ lệ cố định. Nếu thực sự cần benchmark, dùng JMH và so cả direct Java call, exact, invoke matching, invoke adapted, cached adapter exact và invokeWithArguments; tránh đo lookup/init trong vòng lặp nếu mục tiêu là invocation.

### 14.1. Ví dụ đo không công bằng

Nếu vòng lặp exact đã giữ một MethodHandle, còn vòng lặp invoke tạo lookup mới mỗi iteration, kết quả đo chủ yếu là lookup/allocation. Tương tự, nếu chỉ một variant phải boxing và kết quả không được consume, benchmark không đo cùng công việc.

### 14.2. Chọn API theo độ rõ ràng trước

Với code biết type cố định và cần hiệu năng, `invokeExact` thể hiện hợp đồng rõ. Với input từ framework cần conversion hợp lệ, `invoke` hữu ích. Với arguments dạng array và dynamic arity, cân nhắc `invokeWithArguments`. Với public Java method thông thường đã biết tại compile time, direct Java call thường dễ đọc và dễ kiểm soát hơn; không phải mọi method call đều cần MethodHandle.

## 15. Những sai lầm phổ biến

**1.** “invokeExact chỉ kiểm tra arguments.” — Sai: có cả return type.

**2.** “Có thể exact gọi int target rồi cast kết quả thành long.” — Sai: cast quyết định return descriptor, dẫn tới mismatch.

**3.** “Gán kết quả exact từ String target cho Object tự upcast.” — Sai nếu call-site return là Object.

**4.** “Bỏ kết quả exact khi target trả int vẫn hợp lệ.” — Sai: statement context dùng void.

**5.** “invokeExact tự unbox Integer.” — Sai: static argument descriptor phải là int.

**6.** “invokeExact tự cast Object receiver thành String.” — Sai: cần exact String.

**7.** “invoke tự làm mọi conversion.” — Sai: chỉ các chuyển đổi tương thích asType.

**8.** “invoke tự narrow long thành int.” — Sai: kiểu hẹp không được implicit adaptation cho phép.

**9.** “invoke tự parse chuỗi chứa số.” — Sai: không có parsing.

**10.** “Sai arity sẽ được invoke tự thêm đối số.” — Sai với fixed-arity handles.

**11.** “WrongMethodTypeException và ClassCastException là một.” — Sai: không tạo được adapter khác với adapter được tạo nhưng value runtime sai.

**12.** “Unbox null luôn trả 0.” — Sai: có thể NullPointerException.

**13.** “Target throw ArithmeticException thì invoke đổi thành WrongMethodTypeException.” — Sai: target exception vẫn propagate.

**14.** “MethodType.methodType(int,int,int) là ba đối số int.” — Sai: return type trước.

**15.** “findVirtual type chỉ chứa declared args.” — Sai: có receiver.

**16.** “bindTo giữ nguyên type ban đầu.” — Sai: rút receiver argument.

**17.** “asType sửa original handle tại chỗ.” — Sai: trả handle mới.

**18.** “Exact trên adapted handle vẫn phải khớp original type.” — Sai: khớp adapter.type().

**19.** “explicitCastArguments giống hệt asType.” — Sai: hỗ trợ explicit conversions khác.

**20.** “Long narrowing không bao giờ mất dữ liệu.” — Sai: phải validate input.

**21.** “invokeWithArguments giống Method.invoke trong reflection.” — Sai: API và semantics khác.

**22.** “Dùng reflection để gọi MethodHandle.invokeExact sẽ thực hiện normal exact invocation.” — Sai theo Javadoc.

**23.** “Không cần cast null khi exact reference type rõ ràng.” — Dễ sai: static descriptor cho null literal có thể là Void.

**24.** “Một handle exact chạy ở call site này thì site khác luôn chạy.” — Sai: từng site có descriptor riêng.

**25.** “MethodHandle immutable nghĩa target method thread-safe.” — Sai: state đích có thể mutable.

**26.** “Lookup.findStatic thiếu method ném WrongMethodTypeException.” — Không: lookup errors riêng.

**27.** “MethodHandle vượt qua access/module restrictions.” — Sai: Lookup tuân thủ quyền truy cập.

**28.** “Tất cả handles đều có variable arity.” — Sai: phần lớn là fixed arity.

**29.** “invokeWithArguments không bao giờ thất bại do kiểu.” — Sai: conversion/arity vẫn bị kiểm tra.

**30.** “invokeExact luôn nhanh hơn N lần.” — Không có số N chung; cần benchmark.

**31.** “Chỉ nhìn runtime class là biết exact signature.” — Sai: static type/cast tại call site quan trọng.

**32.** “Constructor handle phải trả void vì constructor khai báo không return.” — Sai: xem handle.type() thực tế.

**33.** “Call-site return Object chắc chắn chạy exact với mọi reference.” — Sai: phải trùng return type.

**34.** “MethodHandle.type() không bị ảnh hưởng bởi combinators.” — Sai: adapted handles có thể mang type khác.

**35.** “Catch(Throwable) rồi trả null là cách sửa lỗi typing.” — Sai: che cả lỗi runtime nghiêm trọng của target.

## 16. Checklist cho code review

- [ ] Đã kiểm tra `handle.type()`?
- [ ] Đã phân biệt MethodType khi lookup và MethodType của handle nhận được?
- [ ] Có đủ arguments theo arity?
- [ ] Với virtual method, đã truyền receiver đúng kiểu chưa?
- [ ] Với static method, đã tránh thêm receiver thừa?
- [ ] Với bound handle, đã dùng type sau bindTo chưa?
- [ ] Đối số exact có đúng static types, không chỉ runtime types?
- [ ] Giá trị trả về exact có cast trực tiếp đúng kiểu?
- [ ] Đã hiểu call site expression không cast thường có return Object?
- [ ] Nếu không dùng result, handle có thật sự trả void để exact statement?
- [ ] Null argument exact có ép về đúng reference type khi cần?
- [ ] Khi dùng invoke, conversion có tương thích asType?
- [ ] Không kỳ vọng invoke implicit primitive narrowing?
- [ ] Không kỳ vọng invoke tự parse String thành int?
- [ ] Đã phân biệt WrongMethodTypeException, ClassCastException, NPE?
- [ ] Có xử lý ngoại lệ do chính target ném?
- [ ] Nếu cần adaptation thường xuyên, có xem xét asType tại initialization?
- [ ] Nếu cần narrowing, đã validate miền giá trị trước explicitCastArguments?
- [ ] Có biết asType không sửa original MethodHandle?
- [ ] Với Object arguments, có cân nhắc invokeWithArguments hoặc adapter rõ ràng?
- [ ] Đã phân biệt invokeWithArguments với core reflection?
- [ ] Có tuân thủ Lookup access/modules và không bypass bừa bãi?
- [ ] Nếu target có mutable state, đã đảm bảo thread safety riêng?
- [ ] Đã kiểm thử exact thành công lẫn exact mismatch return/args?
- [ ] Đã kiểm thử invoke widening/unboxing và casting failure?
- [ ] Đã kiểm thử virtual receiver và bound receiver?
- [ ] Đã chạy Java 17+ demos, xác minh đúng output?
- [ ] Khi benchmark, đã tách lookup creation khỏi invocation?
- [ ] Không công bố speedup nếu chưa đo?
- [ ] Không dùng API legacy hoặc assumptions về JDK implementation details?

## 17. Câu hỏi tự kiểm tra

**1.** MethodHandle là gì? — Tham chiếu typed tới một hành vi có thể thực thi.

**2.** MethodType gồm gì? — Return type và danh sách parameter types.

**3.** `MethodType.methodType(int.class,int.class,int.class)` nghĩa gì? — Return int, hai parameters int.

**4.** invokeExact yêu cầu gì? — Call-site descriptor trùng toàn bộ MethodHandle.type().

**5.** invoke xử lý thế nào khi descriptor khớp? — Như invokeExact.

**6.** invoke xử lý thế nào khi descriptor không khớp? — Thử adaptation tương đương asType.

**7.** Exact với return long nhưng handle trả int? — WrongMethodTypeException.

**8.** Invoke với return long và handle trả int? — Có thể widen int→long.

**9.** Exact với Integer nhưng handle nhận int? — WrongMethodTypeException.

**10.** Invoke với Integer nhưng handle nhận int? — Có thể unbox.

**11.** Invoke với long nhưng handle nhận int? — Implicit narrowing bị từ chối.

**12.** Invoke với Object chứa String nhưng target nhận int? — ClassCastException nếu cast/unbox runtime không thành công.

**13.** Null unbox tới primitive gây gì? — NullPointerException.

**14.** Vì sao Object assignment với exact có thể fail? — Return descriptor Object khác return type của handle.

**15.** Vì sao exact statement có thể fail khi target trả int? — Call-site return void mismatch.

**16.** findVirtual khác findStatic ở đâu? — Receiver nằm trong handle type của virtual call.

**17.** String.substring(int,int) virtual handle type gì? — (String,int,int)String.

**18.** bindTo receiver làm gì? — Cố định reference receiver, giảm arity.

**19.** asType có đổi original handle không? — Không, tạo adapter mới.

**20.** Adapter (int,int)long exact được gọi thế nào? — Cast return long với hai int args.

**21.** explicitCastArguments dùng làm gì? — Tạo adapter với explicit conversions, có thể narrowing.

**22.** Rủi ro narrowing là gì? — Mất bits/giá trị.

**23.** insertArguments thay đổi gì? — Cố định một số đối số, thay đổi type handle.

**24.** invokeWithArguments tiện với dạng input nào? — Object[]/danh sách runtime arguments.

**25.** invokeWithArguments giống reflect Method.invoke không? — Không.

**26.** WrongMethodTypeException đến từ đâu? — Mismatch exact hoặc asType adaptation thất bại.

**27.** Target ném ArithmeticException thì sao? — Exception đó propagate.

**28.** Tại sao main demos khai báo throws Throwable? — Invokers có khai báo throws Throwable.

**29.** Lookup thiếu quyền thường báo lỗi gì? — IllegalAccessException.

**30.** Lookup không tìm thấy signature? — NoSuchMethodException.

**31.** MethodHandle immutable có bảo đảm target thread-safe? — Không.

**32.** Có thể exact gọi null mà không cast không? — Nên cast về target reference type để có static descriptor đúng.

**33.** invokeExact có luôn nhanh hơn invoke? — Không có bảo đảm định lượng.

**34.** Khi nào dùng invokeExact? — Khi signature xác định, có thể đảm bảo toàn bộ call-site type khớp.

**35.** Khi nào dùng invoke? — Khi cần conversions asType hợp lệ hoặc API dynamic.

**36.** Muốn biết lý do WMT đầu tiên nên làm gì? — Đọc mh.type(), rồi kiểm tra argument/return static types và receiver.

**37.** Constructor handle luôn có return void không? — Không, xem type của handle sau lookup.

**38.** Các combinators có thể thay đổi MethodType không? — Có.

**39.** Reflective invoke của method placeholder MethodHandle.invokeExact có thay thế actual invocation được không? — Không.

**40.** Quy tắc quan trọng nhất? — invokeExact **khớp tuyệt đối**; invoke **adapt được nếu tương thích asType**.

## 18. Tài liệu chính thức Java SE 17

- [MethodHandle — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html): signature polymorphism, invokeExact, invoke, invokeWithArguments, asType và các lỗi runtime.
- [MethodType — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html): mô tả return/parameter types và các APIs tạo method descriptors.
- [MethodHandles — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html): lookup, insertArguments, explicitCastArguments, invoker và combinators.
- [MethodHandles.Lookup — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): findStatic, findVirtual, constructor/field và access rules.
- [WrongMethodTypeException — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/WrongMethodTypeException.html): không khớp type giữa invocation và handle.
- [JLS §15.12.3 — Java SE 17](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12.3): quy tắc compilation của signature-polymorphic calls.
- [JVMS §5.4.3.3 — Java SE 17](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.3.3): symbolic method reference resolution và signature-polymorphic invokers.

**Ghi nhớ:** `invokeExact` chỉ thành công nếu **cả arguments, receiver và kiểu trả về tại call site** giống hệt `MethodHandle.type()`. `invoke` có thể tạo adaptation tương đương `asType`, cho phép boxing, unboxing, widening và reference cast phù hợp nhưng **không tự thực hiện mọi phép chuyển kiểu**. Nếu muốn exact gọi với một chữ ký khác, hãy xây `asType` adapter mang đúng type rồi gọi exact trên adapter; nếu cần narrowing thì phải có explicit conversion và kiểm tra dữ liệu. Khi lỗi, hãy xem `type()`, static types và cast ở call site thay vì chỉ nhìn các giá trị in ra.