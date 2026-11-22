# 7.5 Phân biệt `WrongMethodTypeException`, `ClassCastException` và lỗi unboxing `null`

Khi gọi một `MethodHandle`, ba lỗi dễ bị nhầm là:

- **`WrongMethodTypeException`**: *kiểu lời gọi* không khớp với `MethodType` của handle, và không thể (hoặc không được phép) thích nghi.
- **`ClassCastException`**: kiểu lời gọi có thể thích nghi, nhưng **giá trị thực tế** không thể ép về kiểu cần thiết; đôi khi lỗi do mã đích hoặc một phép cast ở caller.
- **`NullPointerException` khi unboxing `null`**: bộ thích nghi cần đổi một tham chiếu `null` thành primitive như `int` hoặc `long`. Cũng có các `NullPointerException` khác, chẳng hạn receiver của method instance là `null`.

Ba lỗi cùng có thể xuất hiện trong luồng gọi động. Muốn chẩn đoán chính xác, trước hết cần phân biệt **kiểu của handle**, **kiểu call site**, **giá trị runtime** và **mã đích đang chạy**.

> Ngữ cảnh: Java 17+, các API `java.lang.invoke.MethodHandle`, `MethodType`, `MethodHandles.Lookup`; bài tập trung vào `invokeExact`, `invoke` và bộ thích nghi `asType`.

## 1. Bốn lớp thông tin trước khi phân loại lỗi

Giả sử ta tìm handle của hàm `static int plusOne(int value)`:

~~~java
MethodHandle one = MethodHandles.lookup().findStatic(
        MethodHandleFailureDemo.class,
        "plusOne",
        MethodType.methodType(int.class, int.class));
System.out.println(one.type()); // (int)int
~~~

Đoạn trên chỉ là minh họa bên trong class `MethodHandleFailureDemo`; chương trình chạy đầy đủ nằm ở phần 6.

Ở đây:

1. **Target** là method `plusOne(int)`.
2. **Handle type** là `(int)int`: nhận một `int`, trả một `int`. `MethodType` gồm **cả tham số lẫn kiểu trả về**.
3. **Call-site type** được compiler ghi vào lời gọi signature-polymorphic. Ví dụ `(int) one.invokeExact(4)` yêu cầu `(int)int`; `(Object) one.invokeExact(4)` yêu cầu `(int)Object` dù target vẫn trả `int`.
4. **Giá trị thực tế** có thể là số, chuỗi hoặc `null`. Một call site có kiểu `Object` có thể đưa vào chuỗi `"4"` hoặc `Integer.valueOf(4)`; runtime mới biết giá trị nào chuyển đổi được.

Cú pháp `invokeExact` và `invoke` là **signature-polymorphic**: lời gọi nguồn trông giống một phương thức nhận `Object...`, nhưng JVM dùng descriptor thực được tạo tại vị trí gọi. Java compiler không tự thực hiện các phép đổi tham số thông thường cho hai invoker này; kiểu biểu thức đối số có vai trò quyết định.

Với `invokeExact`, kiểu trả về được suy từ cast trực tiếp của biểu thức gọi, hoặc kiểu ngữ cảnh do Java quy định: không ép kiểu mà dùng kết quả như biểu thức có thể là `Object`; gọi như một statement độc lập có kiểu trả về `void`. Vì vậy chỉ thay ngữ cảnh nhận kết quả cũng có thể tạo `WrongMethodTypeException`.

## 2. Bảng quyết định nhanh

| Triệu chứng | Kiểm tra đầu tiên | Ví dụ | Kết quả điển hình |
| --- | --- | --- | --- |
| `invokeExact` không đúng kiểu tham số, kiểu trả về hoặc số lượng tham số | `handle.type()` so với descriptor của call site | Handle `(int)int`, caller dùng `(long)int` | `WrongMethodTypeException` |
| `invoke` hoặc `asType` cần một chuyển đổi **không thể tồn tại về mặt kiểu** | Có tạo adapter hợp lệ được không? | `String` → `int` qua `asType` | `WrongMethodTypeException` |
| Chuyển đổi kiểu **có thể thực hiện trên lý thuyết**, nhưng đối tượng thực sai kiểu | Kiểu thực tế của giá trị `Object` | `Object value = "4";` rồi cần `int` | `ClassCastException` |
| Cần unbox một giá trị `null` thành primitive | Có `null` tại ranh giới wrapper/reference → primitive không? | `Integer value = null;` dùng với handle nhận `int` | `NullPointerException` |
| Chính target ném lỗi | Đã chạy vào target chưa? Stack trace trỏ vào đâu? | `String.length()` với receiver `null` | `NullPointerException`, **không phải** lỗi unboxing |

Các exception này **không loại trừ** lỗi phát sinh từ chính target: một method được gọi qua handle có thể chủ động ném cả ba loại. Stack trace, nơi exception phát sinh và mã target mới cho biết nguyên nhân.

## 3. `WrongMethodTypeException`: descriptor không phù hợp

### 3.1. `invokeExact`: phải khớp tuyệt đối

Với handle có kiểu `(int)int`:

~~~java
int ok = (int) one.invokeExact(4);       // Thành công
int bad = (int) one.invokeExact(4L);     // WrongMethodTypeException
Object badReturn = (Object) one.invokeExact(4); // WrongMethodTypeException
~~~

Hai dòng lỗi có nguyên nhân khác nhau:

- `4L` có kiểu `long`; call site yêu cầu `(long)int`, khác `(int)int`. `invokeExact` **không** tự thu hẹp `long` về `int`.
- Cast `(Object)` yêu cầu kiểu trả về `Object` tại call site. Dù Java có thể boxing `int` thành `Integer` trong tình huống khác, **`invokeExact` không tự boxing kết quả**.

Ngay cả lời gọi `one.invokeExact(4);` như một statement không sử dụng kết quả cũng yêu cầu return type `void` tại call site và có thể lỗi nếu handle trả `int`. Đừng nhầm với “bỏ qua giá trị trả về” sau một lời gọi `invoke` linh hoạt.

Cách sửa đúng là làm rõ **kiểu thật sự**:

~~~java
int value = (int) one.invokeExact(4);
~~~

Nếu caller cần kiểu khác, chọn `invoke` để cho phép những chuyển đổi được quy định, hoặc tạo adapter với `asType` rồi gọi `invokeExact` theo **đúng kiểu của adapter**.

### 3.2. `invoke`: linh hoạt nhưng không vô hạn

`invoke` cho phép lời gọi có descriptor khác `handle.type()`, về ngữ nghĩa tương đương việc thích nghi handle bằng `asType(callSiteType)` rồi gọi exact:

~~~java
Object boxed = (Object) one.invoke(4); // int trả về được boxing thành Integer
long widened = (long) one.invoke(4);  // int trả về được widening thành long
~~~

Nhưng `(int) one.invoke("4")` vẫn dẫn tới `WrongMethodTypeException`: kiểu tham số tĩnh `String` không có phép chuyển đổi `asType` hợp lệ trực tiếp sang primitive `int`. `asType` không parse chuỗi số `"4"` thành số `4`.

Lỗi cùng loại có thể xảy ra khi số lượng đối số không phù hợp (trừ những quy tắc đặc biệt của handle có khả năng thu thập varargs). Với `asType` trực tiếp, lỗi không thể thích nghi được phát hiện ngay tại thời điểm tạo adapter:

~~~java
one.asType(MethodType.methodType(int.class, String.class));
// WrongMethodTypeException: không có chuyển đổi String -> int hợp lệ
~~~

**Không chữa mọi `WrongMethodTypeException` bằng cách cast bừa sang `Object`.** Việc đổi descriptor có thể khiến cấu trúc hợp lệ nhưng chuyển lỗi sang `ClassCastException` tại runtime. Cần đối chiếu hợp đồng kiểu thật sự và dữ liệu đầu vào.

## 4. `ClassCastException`: adapter hợp lệ, giá trị sai kiểu

Bộ thích nghi `asType` cho phép kiểu tham số `Object` chuyển sang `int` vì `Object` *có thể chứa* một `Integer`. Nhưng giá trị `Object` trong thực tế có thể không phải wrapper số thích hợp.

~~~java
Object candidate = "4";
int result = (int) one.invoke(candidate); // ClassCastException
~~~

Call site yêu cầu kiểu `(Object)int`. Về cấu trúc, chuyển `Object` → `int` được phép: JVM sẽ kiểm tra kiểu wrapper rồi unbox (có thể widening nếu phù hợp). Khi thấy `String`, bước đổi tham chiếu/unbox thất bại nên ném `ClassCastException`.

Phân biệt hai thời điểm:

~~~java
MethodHandle adapter =
        one.asType(MethodType.methodType(int.class, Object.class));
// Tạo adapter THÀNH CÔNG: type = (Object)int

int valid = (int) adapter.invokeExact((Object) Integer.valueOf(4)); // 5
int invalid = (int) adapter.invokeExact((Object) "4");             // ClassCastException
~~~

`invokeExact` trên **adapter** có kiểu `(Object)int` hoàn toàn khớp; lỗi xuất hiện **bên trong bộ thích nghi** khi dữ liệu `"4"` không chuyển thành `int` được.

Trong các trường hợp khác, `ClassCastException` có thể đến từ:

- Một phép cast Java thông thường ở **caller** (không phải bộ thích nghi handle).
- Mã **target** tự cast sai hoặc tự ném exception.
- Adapter khác (ví dụ `asSpreader`/`invokeWithArguments`) phải cast từng đối số.

Hãy xem stack trace và vị trí chuyển đổi. Việc thấy `ClassCastException` **không chứng minh** handle được tạo sai kiểu.

## 5. `NullPointerException` khi unboxing `null`

Unboxing là chuyển từ wrapper/reference về primitive, chẳng hạn `Integer` → `int`. Không có giá trị primitive tương ứng với `null`, nên một chuyển đổi theo quy tắc `asType` từ `null` sang primitive có thể ném `NullPointerException`.

### 5.1. `null` nằm ở tham số

~~~java
Integer boxed = null;
int result = (int) one.invoke(boxed); // NullPointerException khi unbox
~~~

Handle gốc yêu cầu `int`, call site của `invoke` có kiểu tham số `Integer`. Việc thích nghi kiểu có thể thiết lập; lỗi chỉ xuất hiện **khi chạy** vì giá trị cần unbox là `null`.

Nếu dùng `one.invokeExact(boxed)` với call-site argument là `Integer`, trước hết đó là **descriptor không chính xác**, dẫn tới `WrongMethodTypeException`. Bản thân `invokeExact` không tự unbox `Integer` thành `int`.

Lưu ý: biểu thức `(int) (Integer) null` cũng gây NPE do **Java unboxing trước lời gọi**; đây là nguồn lỗi khác với unboxing bên trong adapter.

### 5.2. `null` nằm ở kết quả trả về

Nếu target trả `Integer` và trả thật `null`:

~~~java
MethodHandle nullable = MethodHandles.lookup().findStatic(
        MethodHandleFailureDemo.class,
        "nullableResult",
        MethodType.methodType(Integer.class, int.class));

Integer safe = (Integer) nullable.invokeExact(1); // null, chưa có lỗi
int unsafe = (int) nullable.invoke(1);             // NullPointerException
~~~

Ở dòng thứ hai, call site yêu cầu return type `int`, còn target trả `Integer`; bộ thích nghi cố unbox kết quả `null`. Trả về một tham chiếu `null` **không tự động là lỗi**; lỗi chỉ phát sinh khi một bước tiếp theo cần primitive.

### 5.3. Đừng gộp mọi NPE vào “unboxing null”

Ví dụ `String.length()` được gọi qua handle với receiver `(String) null` cũng ném `NullPointerException`. Đây là **lời gọi instance với receiver null**, không phải unboxing. Tương tự, target có thể tự dereference một field null hoặc tự ném NPE.

Một ngoại lệ khác cần biết: `MethodHandles.explicitCastArguments` có quy tắc chuyển đổi **khác `asType`**; theo Java 17, trong trường hợp chuyển `null` sang primitive, adapter explicit-cast có thể đưa vào **giá trị zero** tương ứng. Vì vậy không áp dụng quy tắc “unbox null luôn NPE” cho **mọi** loại adapter; hãy kiểm tra API đang dùng.

## 6. Chương trình Java 17 chạy hoàn chỉnh, có kết quả xác định

Lưu nguyên chương trình dưới tên **`MethodHandleFailureDemo.java`**. Method `report` bắt ba exception để hiển thị **tên lớp**, tránh phụ thuộc thông báo lỗi có thể khác giữa phiên bản JDK. Các case đã được sắp xếp để một lỗi không chặn các case tiếp theo.

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;

public final class MethodHandleFailureDemo {
    static int plusOne(int value) {
        return value + 1;
    }

    static Integer nullableResult(int ignored) {
        return null;
    }

    @FunctionalInterface
    interface Operation {
        Object run() throws Throwable;
    }

    static void report(String label, Operation operation) {
        try {
            System.out.println(label + " -> " + operation.run());
        } catch (WrongMethodTypeException | ClassCastException | NullPointerException e) {
            System.out.println(label + " -> " + e.getClass().getSimpleName());
        } catch (Throwable e) {
            throw new AssertionError("Unexpected failure: " + label, e);
        }
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodHandle one = lookup.findStatic(
                MethodHandleFailureDemo.class,
                "plusOne", MethodType.methodType(int.class, int.class));

        System.out.println("handle: " + one.type());
        System.out.println("exact: " + (int) one.invokeExact(4));
        report("exact wrong argument", () -> (int) one.invokeExact(4L));
        report("exact wrong return", () -> (Object) one.invokeExact(4));
        report("invoke boxes result", () -> (Object) one.invoke(4));
        report("invoke widens result", () -> (long) one.invoke(4));
        report("impossible call type", () -> (int) one.invoke("4"));

        report("bad dynamic value", () -> {
            Object candidate = "4";
            return (int) one.invoke(candidate);
        });
        report("null unboxing argument", () -> {
            Integer boxed = null;
            return (int) one.invoke(boxed);
        });

        MethodHandle adapter = one.asType(
                MethodType.methodType(int.class, Object.class));
        System.out.println("adapter: " + adapter.type());
        report("adapter wrong value", () -> (int) adapter.invokeExact((Object) "4"));
        report("adapter null", () -> (int) adapter.invokeExact((Object) null));
        report("asType impossible", () -> {
            one.asType(MethodType.methodType(int.class, String.class));
            return "unreachable";
        });

        MethodHandle nullable = lookup.findStatic(
                MethodHandleFailureDemo.class,
                "nullableResult", MethodType.methodType(Integer.class, int.class));
        report("null exact return", () -> (Integer) nullable.invokeExact(1));
        report("null unboxing return", () -> (int) nullable.invoke(1));

        MethodHandle length = lookup.findVirtual(
                String.class, "length", MethodType.methodType(int.class));
        report("null receiver", () -> (int) length.invokeExact((String) null));
    }
}
~~~

Biên dịch và chạy trong thư mục chứa file:

~~~bash
javac --release 17 MethodHandleFailureDemo.java
java MethodHandleFailureDemo
~~~

**Stdout chính xác:**

~~~text
handle: (int)int
exact: 5
exact wrong argument -> WrongMethodTypeException
exact wrong return -> WrongMethodTypeException
invoke boxes result -> 5
invoke widens result -> 5
impossible call type -> WrongMethodTypeException
bad dynamic value -> ClassCastException
null unboxing argument -> NullPointerException
adapter: (Object)int
adapter wrong value -> ClassCastException
adapter null -> NullPointerException
asType impossible -> WrongMethodTypeException
null exact return -> null
null unboxing return -> NullPointerException
null receiver -> NullPointerException
~~~

Đọc kết quả theo nhóm:

1. Hai lỗi `exact wrong ...` chứng minh `invokeExact` khớp **cả kiểu đối số và kiểu trả về**.
2. Hai dòng `invoke boxes result`/`invoke widens result` chứng minh `invoke` có những chuyển đổi hợp lệ; `impossible call type` chứng minh tính linh hoạt có giới hạn.
3. `bad dynamic value`, `adapter wrong value` cùng có `ClassCastException` vì nguồn mang `String` trong khi target cần `int`. Adapter `(Object)int` được tạo thành công trước đó.
4. `null unboxing argument` và `adapter null` đều NPE ở đường chuyển **đối số** thành `int`; `null unboxing return` là NPE ở đường chuyển **kết quả** `Integer` thành `int`.
5. `null exact return` chứng minh trả `null` dưới kiểu `Integer` không có lỗi. `null receiver` minh họa NPE **không liên quan unboxing**.

Chương trình này dùng `throws Throwable` ở `main` vì hai invoker `MethodHandle.invoke`/`invokeExact` khai báo khả năng ném `Throwable`. Trong ứng dụng thực tế, nên xử lý ngoại lệ ở ranh giới gọi động phù hợp, thay vì bắt `Throwable` vô điều kiện và bỏ qua.

## 7. `invokeWithArguments` có khác không?

`invokeWithArguments(Object...)` nhận dữ liệu dưới dạng `Object`, rồi dùng cơ chế chuyển đổi kiểu để gọi target. Nó tiện cho danh sách tham số được xây ở runtime nhưng không phải đường tắt bỏ kiểm tra kiểu. Với handle `one` có kiểu `(int)int` ở chương trình trên, kết quả thường thấy là:

| Lời gọi minh họa (trong `main`) | Kết quả |
| --- | --- |
| `one.invokeWithArguments(4)` | Trả một `Integer` mang giá trị `5` |
| `one.invokeWithArguments()` | `WrongMethodTypeException` do không khớp số đối số |
| `one.invokeWithArguments("4")` | `ClassCastException` vì giá trị `String` không unbox thành `int` được |
| `one.invokeWithArguments(new Object[] { null })` | `NullPointerException` do unboxing `null` |

Với `MethodHandle` là **variable-arity collector**, một số quy tắc đếm đối số khác có thể áp dụng. Đừng suy đoán exception chỉ từ số đối số mà bỏ qua kiểu handle và chế độ varargs.

## 8. Quy trình chẩn đoán cho ứng dụng thực tế

1. **Ghi lại `handle.type()`:** ví dụ `(String,int)long`. Với handle tạo từ instance method, đối số đầu tiên thường là **receiver**. Với handle đã `bindTo`, receiver có thể đã được ràng buộc và biến mất khỏi danh sách tham số.
2. **Xác định call-site descriptor:** xem **kiểu tĩnh** của từng biểu thức đối số, và **kiểu trả về** do cast/ngữ cảnh quyết định. Với `invokeExact`, so sánh *toàn bộ* `MethodType`; đừng chỉ nhìn số lượng đối số.
3. **Xác định kiểu chuyển đổi của `invoke`/`asType`:** `int` ↔ `Object` có thể đòi boxing/unboxing; `Object` → `int` là khả thi về mặt cấu trúc nhưng vẫn phải kiểm tra giá trị. `String` → `int` trực tiếp không phải chuyển đổi `asType` hợp lệ.
4. **Kiểm tra giá trị runtime và nullability:** giá trị nhận được từ JSON, reflection, plugin hoặc map có thể mang `String` thay cho `Integer` hoặc là `null`. Kiểm tra trước khi tạo/gọi adapter.
5. **Phân biệt lỗi adapter với lỗi target:** kiểm tra stack trace và thử target trực tiếp khi có thể. Target tự ném `ClassCastException` hay `NullPointerException` cũng đi qua handle nguyên trạng.
6. **Sửa đúng tầng:** chỉnh call site hoặc `MethodType` khi descriptor sai; chuyển đổi/validate dữ liệu khi runtime value sai; dùng wrapper/null-check/default khi dữ liệu có thể null.

Đoạn validation sau là **helper minh họa**, không phải chương trình chạy độc lập; Java 17 hỗ trợ pattern matching cho `instanceof`:

~~~java
static int requireInt(Object input) {
    if (!(input instanceof Integer number)) {
        throw new IllegalArgumentException("Expected a non-null Integer");
    }
    return number.intValue();
}
~~~

Dùng `requireInt(input)` khi hợp đồng của bạn thực sự đòi `Integer`. Nhờ đó lỗi dữ liệu (chuỗi, `null`) được phát hiện rõ ràng trước khi gọi method handle, thay vì để adapter phát sinh `ClassCastException`/`NullPointerException` ở tầng thấp.

Nếu input được chấp nhận là **chuỗi số**, hãy parse tường minh và xử lý `NumberFormatException`:

~~~java
int number = Integer.parseInt("4"); // 4, chuyển đổi có chủ đích
~~~

`asType` không thực hiện việc parse chuỗi.

Để kiểm tra trực tiếp adapter:

~~~java
MethodType expected = MethodType.methodType(int.class, Object.class);
MethodHandle adapted = one.asType(expected);
System.out.println(adapted.type().equals(expected)); // true
~~~

Adapter có `type()` đúng **không bảo đảm** tất cả giá trị `Object` đều chuyển đổi được khi gọi; kiểm tra input vẫn cần thiết.

## 9. Những ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “`invokeExact` tự boxing/unboxing như một lệnh gọi Java bình thường.” | Descriptor phải khớp chính xác; các phép đổi tự động thuộc `invoke`/adapter khi được cho phép. |
| “Chỉ tham số mới ảnh hưởng tới `WrongMethodTypeException`.” | **Kiểu trả về** của call site cũng tham gia so khớp. |
| “`invoke` luôn sửa được mọi type mismatch.” | `invoke` chỉ thích nghi theo các quy tắc `asType`; mismatch không có phép đổi hợp lệ gây `WrongMethodTypeException`. |
| “Có `asType(Object)` là nhận mọi giá trị Object được.” | Kiểu `Object` có thể hợp lệ về cấu trúc, nhưng giá trị runtime sai kiểu vẫn có thể gây `ClassCastException`. |
| “Chuỗi `"42"` sẽ tự thành `int 42`.” | Không. Muốn parse chuỗi phải gọi API chuyển đổi như `Integer.parseInt`. |
| “`ClassCastException` luôn do `invoke`.” | Caller, một adapter và chính target đều có thể ném ngoại lệ này. |
| “`null` truyền qua handle luôn lỗi ngay.” | `null` là tham chiếu hợp lệ ở vị trí reference; lỗi unboxing chỉ xảy ra khi cần primitive. |
| “Mọi NPE khi gọi handle đều là unboxing.” | Null receiver, dereference trong target và unboxing là các nguyên nhân khác nhau. |
| “Bộ thích nghi nào gặp `null` → primitive cũng NPE.” | `explicitCastArguments` có quy tắc null khác `asType`; phải xem đúng API. |
| “Chỉ nhìn message exception là đủ.” | Kiểm tra `MethodType`, descriptor, giá trị runtime và stack trace; text thông báo có thể thay đổi. |

## 10. Câu hỏi tự kiểm tra

Với `one.type() == MethodType.methodType(int.class, int.class)`, hãy dự đoán exception (hoặc giá trị) của mỗi lời gọi:

1. `(int) one.invokeExact(2L)`
2. `(Object) one.invoke(2)`
3. `Object x = "2"; (int) one.invoke(x)`
4. `Integer x = null; (int) one.invoke(x)`
5. `(int) one.invoke("2")`
6. `(int) one.asType(MethodType.methodType(int.class, Object.class)).invokeExact((Object) Integer.valueOf(2))`

**Đáp án:** (1) `WrongMethodTypeException` vì call site dùng `long`; (2) `Integer(3)` được boxing vào `Object`; (3) `ClassCastException` vì `String` không unbox thành `int`; (4) `NullPointerException` do unboxing `null`; (5) `WrongMethodTypeException` vì kiểu `String` không thể thích nghi trực tiếp thành `int` bằng `asType`; (6) trả `3` vì adapter nhận `Object` mang `Integer(2)` và unbox thành công.

**Tài liệu Java SE 17:**

- [`MethodHandle`: `invokeExact`, `invoke`, `asType`, `invokeWithArguments`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html)
- [`MethodType` và cấu trúc descriptor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html)
- [`WrongMethodTypeException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/WrongMethodTypeException.html)
- [`MethodHandles.explicitCastArguments`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html#explicitCastArguments(java.lang.invoke.MethodHandle,java.lang.invoke.MethodType))