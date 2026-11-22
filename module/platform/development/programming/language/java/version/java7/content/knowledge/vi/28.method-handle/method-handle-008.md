# Cố định đối tượng nhận hoặc tham số bằng `MethodHandle.bindTo` trong Java

## 1. Mục tiêu: một lời gọi có sẵn một đối số cố định

`java.lang.invoke.MethodHandle` biểu diễn một tham chiếu có kiểu rõ ràng, có thể gọi được, đến phương thức, constructor, field hoặc một thao tác đã được biến đổi. Một handle chứa chữ ký ở runtime dưới dạng `MethodType`, nhưng không phải là cùng một thứ với `java.lang.reflect.Method`.

**`MethodHandle.bindTo(Object x)` tạo ra một handle mới bằng cách cố định đối số tham chiếu ĐẦU TIÊN của handle ban đầu.** Khi gọi handle mới, giá trị `x` đã được gắn sẽ được tự chèn vào vị trí đầu tiên, các đối số còn lại được người gọi truyền vào như bình thường. Từ đó handle mới có **ít hơn đúng một tham số** trong chữ ký.

Đây là trọng tâm của mục **“Cố định đối tượng nhận hoặc tham số bằng bindTo”** thuộc nhóm **“MethodHandle”**.

Với một instance method:

~~~text
MethodHandle gốc của String.substring(int,int):
  (String receiver, int begin, int end) -> String
  MethodType: (String,int,int)String

bindTo("abcdef"):
  ("abcdef" đã cố định, int begin, int end) -> String
  MethodType: (int,int)String

invokeExact(1,4) -> "bcd"
~~~

Một handle đến **instance method** có receiver hiện ra như **đối số đầu tiên** của `MethodType`, nên `bindTo(receiver)` đặc biệt thuận tiện: người gọi không phải truyền receiver mỗi lần. Tuy nhiên, `bindTo` không chỉ dùng được cho receiver — một **static method** mà tham số đầu tiên là reference cũng có thể cố định tham số đó.

**Điều kiện cốt lõi:** chỉ cố định được **tham số đầu tiên đang có kiểu tham chiếu**. Nếu tham số đầu tiên là `int`, `long`, `double` hoặc một primitive khác, `bindTo` không hỗ trợ, ngay cả khi caller truyền boxed `Integer`. Để cố định tham số nguyên thủy hoặc đối số ở vị trí khác, dùng `MethodHandles.insertArguments`.

**Special Note (áp dụng đầy đủ):** bài chỉ trình bày kiến thức **vẫn được hỗ trợ và áp dụng trong Java hiện hành**, không lấy hướng dẫn lỗi thời hoặc đã legacy. `MethodHandle` và `bindTo` có từ Java 7 và **vẫn là API còn được hỗ trợ trên Java 17, Java 21 và các JDK mới**. Ví dụ chính dùng JDK 21, không phụ thuộc JDK-internal fields, `Unsafe` hoặc hack reflection.

### Sau bài học, bạn cần nắm

1. `MethodType` của instance vs static handle, và lý do instance receiver đứng đầu.
2. Cách dùng `findVirtual`, `findStatic` và `bindTo` đúng kiểu.
3. Mỗi lần `bindTo` chỉ bỏ **một** leading reference parameter; không gọi target ngay.
4. Chữ ký của handle gốc không thay đổi do method handles là immutable.
5. Cách chain `bindTo` nếu các tham số đứng đầu liên tiếp đều là reference.
6. Khi nào chuyển sang `MethodHandles.insertArguments(target, pos, values...)`.
7. Ngoại lệ `IllegalArgumentException` và `ClassCastException` ở thời điểm bind.
8. Khác biệt `null` được bind thành tham số tham chiếu vs null receiver lúc invoke.
9. Cách gọi `invokeExact` khớp cả tham số lẫn return type, tránh `WrongMethodTypeException`.
10. Việc bind **giữ cùng object reference**, không clone hoặc freeze mutable state.
11. Lưu ý thread-safety, bảo mật capability và chi phí giữ object sống.
12. Chạy chương trình Java 21 có stdout xác định chứng minh tất cả điểm chính.

## 2. Nhắc lại `MethodHandle`, `MethodType` và `Lookup`

### 2.1. Tạo handle cho instance method

~~~java
MethodHandles.Lookup lookup = MethodHandles.lookup();
MethodHandle substring = lookup.findVirtual(
        String.class,
        "substring",
        MethodType.methodType(String.class, int.class, int.class));
~~~

Đây là **mảnh mã minh họa** (cần imports `java.lang.invoke.MethodHandle`, `MethodHandles` và `MethodType`). `String.substring(int,int)` trả về `String` và nhận hai đối số `int`, nên phần `methodType` khi tra cứu method chỉ liệt kê **đối số khai báo của phương thức**, chưa kể receiver.

Sau `findVirtual`, type của handle lại là:

~~~text
(String,int,int)String
~~~

Bởi vì một handle đến instance method cần một receiver kiểu `String` ở **vị trí 0**, tiếp theo mới là `beginIndex` và `endIndex`.

Nếu chưa bind, có thể gọi:

~~~java
String result = (String) substring.invokeExact("abcdef", 2, 5);
~~~

Đây là mảnh minh họa trong context có `substring` và method cho phép `throws Throwable`: kết quả là `"cde"`. Khi dùng `invokeExact` phải truyền **đúng kiểu tĩnh** (ở đây `String`, `int`, `int`) và dùng đúng kiểu return ở call site.

### 2.2. Tạo handle cho static method

Nếu một class có phương thức:

~~~java
private static String label(String prefix, int number) {
    return prefix + number;
}
~~~

Handle tra cứu qua `findStatic` có chữ ký:

~~~text
(String,int)String
~~~

Không có receiver ẩn cần đưa vào `MethodType`; tham số `String prefix` vốn là tham số thứ nhất của static method.

**Kết luận quan trọng:** `bindTo` không biết tham số đầu tiên là *receiver* hay *tham số nghiệp vụ*. Nó nhìn **chữ ký handle hiện tại**, kiểm tra tham số 0 là reference, rồi cố định giá trị đó.

### 2.3. `Lookup` tuân thủ quyền truy cập

`MethodHandles.lookup()` tạo đối tượng `Lookup` có các quyền tương ứng với class gọi. `findVirtual`/`findStatic` không tự bỏ qua Java access control. Ví dụ đầy đủ trong phần 10 dùng `lookup` bên trong chính `BindToExample` để truy cập các static methods `private` của class đó.

Khi cần method riêng tư ở class khác, phải tuân thủ phạm vi module/access thích hợp, ví dụ `privateLookupIn` khi có quyền và module được mở phù hợp. **Không dùng `setAccessible(true)` vô điều kiện hay JDK internal API như một cách “làm bindTo hoạt động”.**

Một handle đã tạo ra là một capability có thể được truyền cho code khác; access checks chủ yếu diễn ra khi handle được tạo, không tự kiểm tra lại `private` mỗi lần invoke. Vì thế **không phát tán những handle cho phép truy cập thao tác nhạy cảm**.

## 3. Cố định receiver: ví dụ `String.substring`

Giả sử cần chạy cùng phương thức `substring` nhiều lần trên **một chuỗi cố định**:

~~~java
MethodHandle substring = lookup.findVirtual(
        String.class,
        "substring",
        MethodType.methodType(String.class, int.class, int.class));

MethodHandle bound = substring.bindTo("abcdef");
String part = (String) bound.invokeExact(1, 4);
~~~

Đây là code minh họa với `lookup` đã khai báo; `part` bằng `"bcd"`. `bindTo("abcdef")` không gọi `substring` ngay; nó chỉ tạo adapter gắn receiver `"abcdef"` và giảm số tham số còn lại.

| Bước | `type()` | Caller truyền khi invoke |
| --- | --- | --- |
| `substring` gốc | `(String,int,int)String` | receiver, begin, end |
| `substring.bindTo("abcdef")` | `(int,int)String` | begin, end |
| `bound.invokeExact(1,4)` | Return `String` | Chỉ hai số nguyên |

### 3.1. Handle gốc vẫn gọi được

~~~java
MethodHandle bound = substring.bindTo("abcdef");
String a = (String) bound.invokeExact(1, 4); // "bcd"
String b = (String) substring.invokeExact("abcdef", 2, 5); // "cde"
~~~

`bindTo` **không sửa** handle `substring` cũ. Một `MethodHandle` là đối tượng immutable về thao tác, chữ ký và target logic, nên kết quả `substring.type()` vẫn `(String,int,int)String`, còn `bound.type()` là `(int,int)String`.

Việc adapter immutable **không có nghĩa receiver được bảo vệ khỏi mutation** nếu receiver là mutable object (ví dụ `StringBuilder`). Chỉ thông tin binding cố định, không phải toàn bộ dữ liệu bên trong object.

### 3.2. Bind receiver của interface/virtual method

`findVirtual` có cơ chế dispatch giống lời gọi virtual tương ứng: phương thức override trên receiver thực tế vẫn có thể được gọi. `bindTo` cố định **instance reference**, không nhất thiết khóa cứng implementation method ở class gốc. Nếu binding cần semantics đặc biệt của `invokespecial`, phải chọn lookup khác cho `findSpecial` theo quyền truy cập; `bindTo` không biến virtual lookup thành special lookup.

### 3.3. Bind không phải “curry mọi đối số”

`bindTo` **chỉ xử lý một leading reference argument**. Với `substring` sau khi bind receiver, leading argument tiếp theo là `int begin`. Bạn **không thể gọi**:

~~~java
MethodHandle invalid = bound.bindTo(Integer.valueOf(1));
~~~

để bind `beginIndex`. Dù giá trị được đóng hộp thành `Integer`, chữ ký handle vẫn là `(int,int)String`, nên `bindTo` ném `IllegalArgumentException`. Muốn cố định số nguyên, dùng `insertArguments`.

## 4. Cố định tham số đầu tiên của static method

`bindTo` không giới hạn ở receiver. Một static method có leading reference parameter rất phù hợp để tạo adapter dùng lại:

~~~java
private static String label(String prefix, int number) {
    return prefix + number;
}

MethodHandle base = lookup.findStatic(
        BindToExample.class,
        "label",
        MethodType.methodType(String.class, String.class, int.class));

MethodHandle withPrefix = base.bindTo("ORD-");
String value = (String) withPrefix.invokeExact(7);
~~~

Đây là snippet minh họa trong `BindToExample` với `lookup` có sẵn; kết quả `value` là `"ORD-7"`.

| Handle | Chữ ký |
| --- | --- |
| `base` | `(String,int)String` |
| `withPrefix` | `(int)String` |

`withPrefix` giống một function đã được cấu hình sẵn `prefix`. Không cần truyền `"ORD-"` mỗi lần. Khi làm các adapter tổng quát, hãy thiết kế API nhận đúng `MethodHandle` đã bind và hiểu rõ lifetime của object được bind.

### 4.1. Bind nhiều reference arguments nối tiếp

Với phương thức:

~~~java
private static String triple(String left, String middle, String right) {
    return left + "|" + middle + "|" + right;
}
~~~

Handle có `(String,String,String)String`. Vì **cả hai tham số đầu sau mỗi lần bind đều là reference**, có thể:

~~~java
MethodHandle twice = allReferences.bindTo("left").bindTo("middle");
String result = (String) twice.invokeExact("right");
~~~

Kết quả: `"left|middle|right"`.

Chữ ký chuyển dần:

~~~text
(String,String,String)String
  .bindTo("left")    -> (String,String)String
  .bindTo("middle")  -> (String)String
  invokeExact("right") -> "left|middle|right"
~~~

Lưu ý nếu chuỗi parameters ở đầu xen `int` hay `double`, việc chain sẽ dừng khi leading parameter là primitive. `bindTo` không cho bind “nhảy qua” một tham số để tới tham số tiếp theo.

### 4.2. Bind một object nhận nhưng còn tham số method

Ví dụ `StringBuilder.append(String)` có handle type `(StringBuilder,String)StringBuilder`. Bind receiver `StringBuilder` sẽ được handle `(String)StringBuilder`. Caller chỉ truyền suffix. Mọi lời gọi adapter vẫn tác động lên **cùng StringBuilder**.

Điều này tạo convenience API, nhưng rất khác với gắn một immutable `String`: tác động phụ và thread-safety thuộc object `StringBuilder`, không được `bindTo` xử lý.

## 5. `bindTo` vs `MethodHandles.insertArguments`

Nếu cần cố định **tham số nguyên thủy**, hoặc **một tham số không ở vị trí đầu**, phương thức thích hợp là:

~~~java
MethodHandles.insertArguments(target, pos, values...);
~~~

Tham số `pos` là **vị trí bắt đầu** trong danh sách tham số của `target` (0-based). `values` là các giá trị sẽ được ràng buộc vào các tham số liên tiếp ở đó. Phương thức này có thể xử lý primitive và reference parameters, kể cả ở giữa/cuối, theo các quy tắc chuyển đổi giá trị của API.

| Nhu cầu | `bindTo(x)` | `insertArguments(handle,pos,...)` |
| --- | --- | --- |
| Bind receiver instance method | Tốt nếu receiver đứng đầu và có reference type | Được, thường `pos=0` |
| Bind leading `String`/`Object` param của static method | Được | Được |
| Bind leading `int`/`long` | **Không** | Được |
| Bind tham số ở vị trí 1, 2… | **Không trực tiếp** | Được |
| Bind nhiều đối số liên tiếp một lần | Chỉ từng lần, khi mọi leading type là reference | Có |
| Bind nonleading reference | Không, trừ khi đã biến đổi chữ ký khác | Được |
| Kết quả | Adapter mới, target không đổi | Adapter mới, target không đổi |

### 5.1. Bind primitive `int` ở đầu

Sau `withPrefix = base.bindTo("ORD-")`, type là `(int)String`. Muốn cố định luôn số 7:

~~~java
MethodHandle noArgs = MethodHandles.insertArguments(withPrefix, 0, 7);
String result = (String) noArgs.invokeExact();
~~~

Kết quả `"ORD-7"`; chữ ký `noArgs` giờ là `()String`. Nếu gọi `withPrefix.bindTo(Integer.valueOf(7))` sẽ ném `IllegalArgumentException` vì first type là primitive.

### 5.2. Bind primitive ở vị trí 1

Handle static `base` có type `(String,int)String`. Để cố định **số 7** mà vẫn để caller cung cấp prefix:

~~~java
MethodHandle fixedNumber = MethodHandles.insertArguments(base, 1, 7);
String result = (String) fixedNumber.invokeExact("X-");
~~~

Kết quả `"X-7"`. Chữ ký từ `(String,int)String` chuyển thành `(String)String`. `bindTo` không thể ràng buộc trực tiếp `int` tại index 1.

### 5.3. Bind nonleading reference

Với static handle `(int,String)String` (ví dụ method `withSuffix`), muốn cố định suffix ở index 1:

~~~java
MethodHandle fixedSuffix =
        MethodHandles.insertArguments(suffixHandle, 1, "!");
String value = (String) fixedSuffix.invokeExact(9);
~~~

Kết quả `"9!"`. Đối số đứng đầu của `suffixHandle` là `int`, nên `suffixHandle.bindTo("!")` không thể dùng, dù đối số mà bạn muốn cố định là reference.

### 5.4. `insertArguments` không thay đổi target gốc

Giống `bindTo`, `insertArguments` trả **handle mới**, không mutate original. Sau khi bind, in `handle.type()` để kiểm tra đúng arity và parameter types trước khi gọi `invokeExact`; đó là một kỹ thuật debug hiệu quả.

### 5.5. Không nhầm với `dropArguments`

`MethodHandles.dropArguments` làm điều **ngược về số tham số**: thêm những tham số giả bị bỏ qua trước khi gọi target; nó không cố định giá trị. `permuteArguments` thay đổi thứ tự/ánh xạ tham số; `filterArguments` biến đổi các giá trị. Khi chỉ cần gắn một object reference đầu tiên, `bindTo` đơn giản hơn các tổ hợp phức tạp đó.

## 6. Lỗi có thể xảy ra ngay khi `bindTo`

Theo Java SE 21 Javadoc, có hai trường hợp quan trọng ở **thời điểm tạo adapter**:

1. **`IllegalArgumentException`:** target không có leading parameter **kiểu reference**. Có thể vì handle không có tham số nào hoặc parameter 0 là primitive.
2. **`ClassCastException`:** giá trị `x` không thể convert/cast sang leading reference parameter type của target.

### 6.1. Leading primitive

~~~java
// withPrefix.type() == (int)String
withPrefix.bindTo(Integer.valueOf(7));
~~~

Phương thức này **ném `IllegalArgumentException`**, không tự box/unbox thành một `int` đã bind. `bindTo(Object)` nhận `Object` ở source level không có nghĩa nó có thể cố định mọi kiểu trong `MethodType`.

### 6.2. Không có leading parameter

~~~java
MethodHandle constant = MethodHandles.constant(String.class, "fixed");
// constant.type() == ()String
constant.bindTo("any");
~~~

`constant` không nhận tham số, nên `bindTo` ném `IllegalArgumentException`. Đây không phải lỗi của giá trị `"any"` mà là handle không có parameter 0.

### 6.3. Sai kiểu tham chiếu

~~~java
// base.type() == (String,int)String
base.bindTo(new Object());
~~~

Leading parameter cần `String`, nhưng `new Object()` không thể cast sang `String`. Lời gọi `bindTo` ném **`ClassCastException`** khi tạo adapter.

Nếu bạn có handle nhận `CharSequence`, một `StringBuilder` có thể đáp ứng type `CharSequence`; nhưng nếu target nhận chính xác `String` thì `StringBuilder` không tự được chuyển thành String. `bindTo` không tự gọi `toString()`.

### 6.4. Null có thể bind — nhưng khi invoke lại là chuyện khác

`null` là một reference có thể bind cho parameter kiểu reference:

~~~java
MethodHandle nullable = lookup.findStatic(
        BindToExample.class, "nullable",
        MethodType.methodType(String.class, String.class));
MethodHandle fixedNull = nullable.bindTo(null);
String answer = (String) fixedNull.invokeExact();
~~~

Nếu `nullable(String)` trả `"(null)"` khi nhận null như ví dụ đầy đủ, `answer` chính là `"(null)"`. Bản thân việc bind null **không tự ném NPE** chỉ vì reference bằng null.

Nhưng khác hẳn nếu cố định receiver của instance method:

~~~java
MethodHandle upper = lookup.findVirtual(
        String.class, "toUpperCase",
        MethodType.methodType(String.class));
MethodHandle nullReceiver = upper.bindTo(null);
String s = (String) nullReceiver.invokeExact(); // NPE lúc invoke.
~~~

`bindTo(null)` trên handle có receiver kiểu `String` có thể tạo adapter, nhưng khi thực thi `String.toUpperCase()` với receiver null, việc dereference thất bại và ném `NullPointerException`. **Đừng đồng nhất exception tại binding với exception của target tại invocation.**

### 6.5. Các lỗi khác ở invocation

Ngay cả khi bind thành công, target có thể ném exceptions nghiệp vụ, `NullPointerException` khi làm việc với object state, hoặc `WrongMethodTypeException` nếu caller dùng `invokeExact` sai chữ ký. `bindTo` không nuốt, đổi thành giá trị mặc định hay “bảo đảm” target sẽ chạy thành công.

## 7. `invokeExact` cần khớp chữ ký hiện tại sau bind

`invokeExact` là một **signature-polymorphic method**. Tại call site, Java sử dụng **kiểu tĩnh thực sự của đối số và biểu thức trả về** để tạo method type mong muốn. Handle phải có type khớp chính xác, bao gồm return type.

Sau khi:

~~~java
MethodHandle withPrefix = base.bindTo("ORD-");
// withPrefix.type() == (int)String
~~~

Cách gọi đúng:

~~~java
String output = (String) withPrefix.invokeExact(7);
~~~

Đối số `7` có kiểu `int`, return được sử dụng như `String` nên call site match `(int)String`.

**Sai:**

~~~java
Object output = (Object) withPrefix.invokeExact(7);
~~~

Đây là **phản ví dụ**: call site mong return `Object`, nhưng handle thực trả `String`. `invokeExact` không tự thích nghi như một phép gán thông thường; nó ném `WrongMethodTypeException`.

Một sai lầm tương tự là viết:

~~~java
String output = (String) withPrefix.invokeExact(Integer.valueOf(7));
~~~

Caller truyền `Integer` thay `int` vào `(int)String`, nên kiểu không khớp chính xác. Nếu API cần conversions có kiểm soát, có thể xem `invoke` hoặc `asType`, nhưng phải hiểu conversions và exceptions. Trong ví dụ học thuật về `bindTo`, `invokeExact` làm thay đổi chữ ký dễ nhìn thấy hơn.

### 7.1. Đọc `type()` thay vì đoán

~~~java
System.out.println(base.type());       // (String,int)String
System.out.println(withPrefix.type()); // (int)String
~~~

Trong JDK 21, `MethodType.toString()` biểu diễn chữ ký kiểu trên. Các lời gọi `type()` rất hữu ích khi debug `bindTo`, `insertArguments`, `filterArguments` hoặc `asType`.

### 7.2. `invoke` và `invokeWithArguments`

- `invokeExact`: đòi method type của caller **khớp hoàn toàn**.
- `invoke`: cho phép một số chuyển đổi giống `asType` trong quá trình gọi.
- `invokeWithArguments`: cơ chế varargs tương đối tổng quát, có nhiều conversions/boxing và overhead hơn; không nên dùng chỉ để né việc hiểu `MethodType`.

**Cảnh báo:** bản thân `bindTo` không làm handle “dynamically typed”. Handle sau bind vẫn có một `MethodType` cụ thể, nên hãy biết chính xác kiểu parameters và return.

### 7.3. Return type của void methods

Nếu target trả `void`, bound handle cũng trả `void` — `bindTo` không thay return type. Gọi `invokeExact` trên handle `()void` phải đặt trong context không yêu cầu `String`/`Object`. Không thể chỉ cast output của một void handle.

## 8. Object được bind: giữ reference, không sao chép snapshot

Đây là phần quan trọng khi dùng `bindTo` với receiver mutable:

~~~java
StringBuilder builder = new StringBuilder("A");
MethodHandle append = lookup.findVirtual(
        StringBuilder.class, "append",
        MethodType.methodType(StringBuilder.class, String.class));
MethodHandle boundAppend = append.bindTo(builder);

StringBuilder returned = (StringBuilder) boundAppend.invokeExact("-B");
StringBuilder again = (StringBuilder) boundAppend.invokeExact("-C");
~~~

Sau hai lần invoke, **cùng object** `builder` chứa `"A-B-C"`. `boundAppend` giữ reference tới `builder` đã bind; mỗi lời gọi làm việc với **trạng thái hiện tại** của builder, không reset về `"A"`.

### 8.1. Handle immutable, dữ liệu target mutable

- `MethodHandle` đã bind là adapter immutable: không đổi method type, binding hoặc target sau khi tạo.
- Object được bind có thể là `StringBuilder`, `List`, session, connection hoặc một service có internal mutable state.
- Mutation sau khi bind vẫn có thể quan sát được qua những lần invoke tiếp theo.
- `bindTo` không deep copy, không clone, không rollback và không đồng bộ hóa object.

### 8.2. Một bound receiver có thể sống lâu

Nếu một handle được giữ lâu trong static map, cache hoặc callback registry, giá trị `x` đã bind cũng có thể bị giữ reachable lâu, tùy object graph. **Không bind một request/session rất lớn vào singleton rồi quên giải phóng handle khỏi cache**. Đây là vấn đề lifetime và memory retention, không phải “memory leak” của API `bindTo` tự thân.

### 8.3. Thread safety không tăng nhờ bind

`StringBuilder` không phải mutable object thread-safe. Nếu nhiều threads cùng gọi một `boundAppend` trỏ tới cùng builder, các phép append có thể race. MethodHandle có thể được chia sẻ để gọi, nhưng **target object và target operation** phải đáp ứng concurrency contract.

Tương tự, một database `Connection` hoặc stateful service được bind vào handle không trở nên thread-safe; không dùng một bound connection trên nhiều threads khi driver/ownership contract không cho phép.

### 8.4. Bound value có thể là secret/capability

Nếu bind một token, privileged service, file handle hoặc object có quyền thao tác nhạy cảm, bản thân handle mới **nắm giữ reference đó**. Code có được handle có thể thực hiện thao tác target trong giới hạn interface mà handle cho phép. Không publish handle nhạy cảm tới untrusted code. Khi debug, không log `toString()` của bound object chứa secrets.

## 9. Những trường hợp `bindTo` hữu ích trong thực tế

### 9.1. Tạo callable gắn sẵn receiver

Một adapter có thể gắn một instance target và chỉ để caller cung cấp các tham số còn lại, ví dụ một method `service.process(Input)` trở thành `(Input)Result`. Điều này gần với **partial application** và các closures/lambda:

~~~java
MethodHandle process = lookup.findVirtual(
        Service.class, "process",
        MethodType.methodType(Result.class, Input.class));
MethodHandle forService = process.bindTo(service);
~~~

Đây là **sơ đồ mã minh họa**, `Service`, `Result`, `Input` và `service` do ứng dụng định nghĩa. `forService.type()` sẽ là `(Input)Result` nếu lookup thành công. Đừng dùng nó để bypass service lifetime, security hoặc ownership.

### 9.2. Tạo handler có cấu hình tĩnh

Với `static String format(String prefix, int code)`, `formatHandle.bindTo("ERR-")` có thể tạo callable chỉ nhận `int`. Nếu yêu cầu gắn thêm một int cụ thể, dùng `insertArguments` như phần 5.

Đây là pattern hữu ích trong dynamic dispatch, generated adapters, method-handle pipelines hoặc thư viện cần lưu method references có type cố định.

### 9.3. Composition với các adapters khác

`MethodHandles` cung cấp các combinators như `filterArguments`, `filterReturnValue`, `asType`, `permuteArguments`, `dropArguments` và `insertArguments`. Có thể dùng chúng để lắp pipeline có type rõ:

~~~text
MethodHandle gốc
   |
   +-- bindTo(receiver) ----> bớt leading reference param
   |
   +-- insertArguments(...) -> bớt param ở vị trí chọn
   |
   +-- asType(...) ---------> đổi signature qua conversions cho phép
   |
   +-- invokeExact(...) ----> caller type match handle type hiện tại
~~~

Đây là **sơ đồ khái niệm**, không phải lời khuyên áp từng phép biến đổi không cần thiết. Mỗi bước có rule về type, count, return và exception. In `handle.type()` sau từng adapter để tránh cấu trúc quá khó debug.

### 9.4. Khi lambda hoặc method reference dễ đọc hơn

Để cố định một receiver đơn giản trong app code, đôi khi:

~~~java
java.util.function.IntFunction<String> operation = n -> label("ORD-", n);
~~~

dễ hiểu hơn tìm `MethodHandle`, nhất là khi target/method name đã biết lúc biên dịch. `bindTo` hữu ích hơn khi API thực sự làm việc với **MethodHandle values và dynamic composition**. Không ép mọi callback thành method handle vì tin rằng chắc chắn nhanh hơn lambda.

## 10. Chương trình Java 21 hoàn chỉnh: kiểm chứng bind receiver và tham số

Chương trình sau không cần dependency ngoài JDK, không truy cập mạng/files nghiệp vụ và in output **xác định**. Nó minh họa:

1. `findVirtual(String.substring)` với receiver đứng đầu; bind `"abcdef"` và kiểm tra chữ ký thay đổi.
2. Handle gốc vẫn giữ type/behavior sau `bindTo`.
3. `findStatic(label)` và bind tham số `prefix`.
4. Chain hai lần `bindTo` cho hai tham số reference liên tiếp.
5. `insertArguments` cố định primitive đầu và primitive không nằm đầu, rồi cố định tham số `String` ở cuối.
6. Kiểm chứng `IllegalArgumentException` khi leading primitive hoặc handle không có parameters.
7. Kiểm chứng `ClassCastException` khi giá trị không cast được sang leading reference type.
8. Bind null cho static reference argument; bind null cho receiver thì đến lúc invoke mới ném `NullPointerException`.
9. Bind `StringBuilder` mutable rồi gọi nhiều lần để thấy cùng object bị cập nhật.
10. Kiểm chứng `WrongMethodTypeException` khi call site của `invokeExact` mong `Object` thay vì `String`.

### 10.1. File Java biên dịch và chạy được

Tạo `src/main/java/demo/BindToExample.java`:

~~~java
package demo;

import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;

public final class BindToExample {
    private BindToExample() {}

    private static String label(String prefix, int number) {
        return prefix + number;
    }

    private static String triple(String left, String middle, String right) {
        return left + "|" + middle + "|" + right;
    }

    private static String withSuffix(int number, String suffix) {
        return number + suffix;
    }

    private static String nullable(String text) {
        return text == null ? "(null)" : text;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        MethodHandle substring = lookup.findVirtual(
                String.class, "substring",
                MethodType.methodType(String.class, int.class, int.class));
        MethodHandle boundSubstring = substring.bindTo("abcdef");
        System.out.println("lookup-substring-type=" + substring.type());
        System.out.println("bound-substring-type=" + boundSubstring.type());
        System.out.println("substring=" +
                (String) boundSubstring.invokeExact(1, 4));
        System.out.println("original-still-works=" +
                (String) substring.invokeExact("abcdef", 2, 5));

        MethodHandle staticLabel = lookup.findStatic(
                BindToExample.class, "label",
                MethodType.methodType(String.class, String.class, int.class));
        MethodHandle boundPrefix = staticLabel.bindTo("ORD-");
        System.out.println("static-original-type=" + staticLabel.type());
        System.out.println("static-bound-type=" + boundPrefix.type());
        System.out.println("static-label=" +
                (String) boundPrefix.invokeExact(7));

        MethodHandle allReferences = lookup.findStatic(
                BindToExample.class, "triple",
                MethodType.methodType(String.class,
                        String.class, String.class, String.class));
        MethodHandle twiceBound = allReferences.bindTo("left").bindTo("middle");
        System.out.println("chain-type=" + twiceBound.type());
        System.out.println("chain=" +
                (String) twiceBound.invokeExact("right"));

        MethodHandle primitiveFirst =
                MethodHandles.insertArguments(boundPrefix, 0, 7);
        System.out.println("insert-leading-primitive=" +
                (String) primitiveFirst.invokeExact());

        MethodHandle primitiveAtOne =
                MethodHandles.insertArguments(staticLabel, 1, 7);
        System.out.println("insert-nonleading-primitive=" +
                (String) primitiveAtOne.invokeExact("X-"));

        MethodHandle suffixHandle = lookup.findStatic(
                BindToExample.class, "withSuffix",
                MethodType.methodType(String.class, int.class, String.class));
        MethodHandle fixedSuffix =
                MethodHandles.insertArguments(suffixHandle, 1, "!");
        System.out.println("insert-last-reference=" +
                (String) fixedSuffix.invokeExact(9));

        boolean primitiveRejected = false;
        try {
            boundPrefix.bindTo(Integer.valueOf(7));
        } catch (IllegalArgumentException expected) {
            primitiveRejected = true;
        }
        System.out.println("bad-primitive-iae=" + primitiveRejected);

        boolean wrongClassRejected = false;
        try {
            staticLabel.bindTo(new Object());
        } catch (ClassCastException expected) {
            wrongClassRejected = true;
        }
        System.out.println("bad-reference-cce=" + wrongClassRejected);

        boolean noLeadingParameterRejected = false;
        try {
            MethodHandles.constant(String.class, "fixed").bindTo("not-used");
        } catch (IllegalArgumentException expected) {
            noLeadingParameterRejected = true;
        }
        System.out.println("zero-arity-iae=" + noLeadingParameterRejected);

        MethodHandle nullableHandle = lookup.findStatic(
                BindToExample.class, "nullable",
                MethodType.methodType(String.class, String.class));
        MethodHandle nullFixed = nullableHandle.bindTo(null);
        System.out.println("nullable-bound=" +
                (String) nullFixed.invokeExact());

        MethodHandle toUpper = lookup.findVirtual(
                String.class, "toUpperCase",
                MethodType.methodType(String.class));
        MethodHandle nullReceiver = toUpper.bindTo(null);
        boolean nullReceiverNpe = false;
        try {
            String ignored = (String) nullReceiver.invokeExact();
        } catch (NullPointerException expected) {
            nullReceiverNpe = true;
        }
        System.out.println("null-receiver-npe=" + nullReceiverNpe);

        StringBuilder builder = new StringBuilder("A");
        MethodHandle append = lookup.findVirtual(
                StringBuilder.class, "append",
                MethodType.methodType(StringBuilder.class, String.class));
        MethodHandle boundAppend = append.bindTo(builder);
        System.out.println("builder-before=" + builder);
        System.out.println("builder-bound-type=" + boundAppend.type());
        StringBuilder returned = (StringBuilder) boundAppend.invokeExact("-B");
        StringBuilder ignored = (StringBuilder) boundAppend.invokeExact("-C");
        System.out.println("builder-after=" + builder);
        System.out.println("builder-same=" + (returned == builder));

        boolean wrongExactType = false;
        try {
            Object value = (Object) boundPrefix.invokeExact(7);
        } catch (WrongMethodTypeException expected) {
            wrongExactType = true;
        }
        System.out.println("invokeExact-wmt=" + wrongExactType);
    }
}
~~~

### 10.2. Lệnh biên dịch và chạy

Từ thư mục chứa `src`, dùng JDK 21:

~~~sh
javac --release 21 -encoding UTF-8 -Xlint:all -d out src/main/java/demo/BindToExample.java
java -cp out demo.BindToExample
~~~

Ví dụ dùng Java 21, chỉ cần `java.base`. Các exception dự kiến được bắt thành boolean để stdout ổn định, không in stack trace bất định. `main` khai báo `throws Throwable` vì `MethodHandle.invokeExact` cho phép target throw bất kỳ `Throwable`; khi viết ứng dụng thật, bắt và xử lý các lỗi theo contract cụ thể thay vì nuốt mọi exception.

### 10.3. Stdout chính xác đã kiểm thử

~~~text
lookup-substring-type=(String,int,int)String
bound-substring-type=(int,int)String
substring=bcd
original-still-works=cde
static-original-type=(String,int)String
static-bound-type=(int)String
static-label=ORD-7
chain-type=(String)String
chain=left|middle|right
insert-leading-primitive=ORD-7
insert-nonleading-primitive=X-7
insert-last-reference=9!
bad-primitive-iae=true
bad-reference-cce=true
zero-arity-iae=true
nullable-bound=(null)
null-receiver-npe=true
builder-before=A
builder-bound-type=(String)StringBuilder
builder-after=A-B-C
builder-same=true
invokeExact-wmt=true
~~~

### 10.4. Giải nghĩa từng nhóm kết quả

| Output | Điều được xác nhận |
| --- | --- |
| `lookup-substring-type=(String,int,int)String` | Instance receiver đứng đầu chữ ký của `findVirtual` handle |
| `bound-substring-type=(int,int)String` | `bindTo("abcdef")` loại bỏ đúng một leading reference param |
| `substring=bcd` | Bound handle chèn sẵn receiver rồi thực thi substring |
| `original-still-works=cde` | Handle gốc không bị thay đổi |
| `static-original-type=(String,int)String` | Static handle không có receiver ẩn |
| `static-bound-type=(int)String` | Static leading reference `prefix` cũng bind được |
| `static-label=ORD-7` | Giá trị prefix cố định chính xác |
| `chain-type=(String)String` | Hai `bindTo` liên tiếp bỏ hai leading references |
| `chain=left\|middle\|right` | Các tham số còn lại giữ nguyên thứ tự |
| `insert-leading-primitive=ORD-7` | `insertArguments` bind được `int` |
| `insert-nonleading-primitive=X-7` | `insertArguments` bind vị trí 1 |
| `insert-last-reference=9!` | `insertArguments` bind nonleading String |
| `bad-primitive-iae=true` | `bindTo` từ chối leading primitive |
| `bad-reference-cce=true` | Giá trị bind sai reference type bị cast lỗi |
| `zero-arity-iae=true` | Không có parameter để bind |
| `nullable-bound=(null)` | Có thể bind null thành static reference argument |
| `null-receiver-npe=true` | Null receiver có thể bind, nhưng method invocation thất bại |
| `builder-before=A` / `builder-after=A-B-C` | Cùng mutable receiver được dùng nhiều lần |
| `builder-same=true` | `StringBuilder.append` trả về chính receiver |
| `invokeExact-wmt=true` | Return type của call site không khớp handle |

### 10.5. Vì sao chương trình đáng tin để test?

- Không có random, network, database, clock hoặc concurrent scheduling.
- `MethodHandle.type()` được JDK trình bày có kiểu rõ ràng, không phụ thuộc object identity.
- `String.substring`, static methods và `StringBuilder.append` có output xác định.
- Exception được bắt **đúng loại** theo API `bindTo` và `invokeExact`.
- `invokeExact` được biên dịch với static argument/return types khớp trong các trường hợp thành công.
- Java code trong khối `~~~java` là chương trình đầy đủ; các snippets ở các phần khác được gắn nhãn minh họa.

## 11. Các tình huống thiết kế thường gặp

### 11.1. Có nên bind một service singleton?

Chỉ nếu service được phép sống lâu và thread-safe theo business contract. Nếu singleton handle giữ receiver có state mutable không thread-safe, nhiều callers dùng handle đó vẫn có thể race. Sự immutable của handle **không bảo vệ** object đã bind.

### 11.2. Có nên bind một request context?

Cần chú ý lifetime: nếu bound handle được lưu ở cache sống lâu hơn request, request context có thể bị giữ trong memory. Nếu request chứa user secrets, đừng vô ý truyền handle tới code không đáng tin cậy. Dùng scope rõ, cleanup/cancel và ownership phù hợp.

### 11.3. Có nên dùng `bindTo` chỉ để tăng performance?

Không chắc. MethodHandle có thể được JVM tối ưu hóa tốt khi call site ổn định, nhưng lợi ích phụ thuộc JIT warm-up, type shapes, target inlining và pattern sử dụng. So sánh với lời gọi trực tiếp, lambda, method reference và reflection bằng benchmark đúng điều kiện; không tự khẳng định `bindTo` luôn nhanh hơn.

### 11.4. Có nên cache bound handles?

Nếu receiver/config cố định và được gọi nhiều lần, cache có thể tiết kiệm chi phí lắp adapter. Nhưng cache keys, invalidation và memory-retention phải đúng. Không cache vô hạn một bound handle mới cho mỗi request ID/customer object.

### 11.5. `bindTo` có bảo đảm null safety không?

Không. Null có thể bind vào reference parameter, nhưng target sau đó có thể dereference hoặc validate và ném `NullPointerException`/`IllegalArgumentException`. Xác định nullability của target API, không chỉ của adapter creation.

### 11.6. Có cần kiểm tra receiver type trước khi bind?

Nếu receiver có runtime type không tương thích leading reference param, `bindTo` tự ném `ClassCastException`. Với dữ liệu untrusted hoặc adapter generator, nên xác minh `target.type().parameterCount()>0` và `parameterType(0)` là reference trước khi bind để báo lỗi rõ. Nhưng kiểm tra trước không thay thế error handling vì dynamic target/type có thể thay đổi trong các bước tạo adapter khác.

### 11.7. Bind receiver và khóa trong multi-threaded program

Nếu method cần lock hoặc synchronization, nó vẫn cần những cơ chế đó khi được gọi qua bound handle. `bindTo` **không tạo critical section**. Đừng dùng một `MethodHandle` như lock hay tin rằng adapter immutable thì mọi methods được gọi qua nó đều thread-safe.

## 12. Các lỗi phổ biến và cách khắc phục

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Nghĩ `bindTo` cố định đối số bất kỳ | Không; chỉ leading reference | Dùng `insertArguments` khi khác vị trí/primitive |
| Nghĩ `bindTo(Integer)` bind được leading `int` | `IllegalArgumentException` | `insertArguments(handle,0,7)` |
| Bind reference sai runtime type | `ClassCastException` | Kiểm tra `type().parameterType(0)` và giá trị |
| Bind handle có type `()R` | `IllegalArgumentException` | Không còn parameter để cố định |
| Nghĩ bind null lúc nào cũng ném ngay | Null reference có thể bind | Phân biệt bind-time và invoke-time |
| Bind null receiver rồi gọi virtual method | `NullPointerException` lúc invoke | Validate receiver trước khi bind |
| Gọi handle cũ bằng chữ ký mới | `WrongMethodTypeException` | Dùng đúng original/bound handle và `type()` |
| Gọi `invokeExact` và ép return sang `Object` | Có thể sai exact return type | Cast đúng `String` hoặc điều chỉnh type bằng adapter |
| Nghĩ `bindTo` sửa handle gốc | Original vẫn giữ type/behavior | Lưu biến bound handle mới |
| Nghĩ handle immutable nghĩa receiver immutable | Mutable receiver vẫn đổi | Áp ownership/thread-safety riêng |
| Cất bound request context vào static cache vô hạn | Có thể giữ object sống quá lâu | Cache lifecycle/eviction rõ |
| Chia sẻ bound `StringBuilder` giữa threads | Race trên object mutable | Dùng thread confinement/synchronization |
| Bind privileged object rồi public handle | Rò quyền truy cập tới target | Giữ capability private, kiểm soát phát tán |
| Dùng `findVirtual` như static method | Lookup sai dạng | `findStatic` cho static, `findVirtual` cho instance |
| Bỏ qua Java access control của `Lookup` | Tra cứu không hợp lệ/exception | Dùng lookup có quyền hợp lệ |
| Trông đợi bind tự execute method | Không có side effect của target tại bind | Phải invoke handle mới |
| Dùng `bindTo` để “snapshot” mutable object | Không clone object | Copy state riêng nếu cần snapshot |
| Tối ưu hóa không có benchmark | Code khó đọc, chưa chắc nhanh | Benchmark đúng workload |

## 13. Bài tập có lời giải

**Câu 1.** `findVirtual(String.substring(int,int))` trả handle có type gì?  
**Đáp án:** `(String,int,int)String`, với `String` receiver ở đầu.

**Câu 2.** Sau `bindTo("abcdef")` còn type gì?  
**Đáp án:** `(int,int)String`.

**Câu 3.** `bound.invokeExact(1,4)` trên `"abcdef"` trả gì?  
**Đáp án:** `"bcd"` nếu dùng đúng return type `String` ở call site.

**Câu 4.** `bindTo` có gọi target method ngay không?  
**Đáp án:** Không. Nó tạo adapter, target chỉ được gọi lúc invoke.

**Câu 5.** Bind có thay đổi handle cũ không?  
**Đáp án:** Không. Original handle immutable, type vẫn giữ nguyên.

**Câu 6.** `bindTo` chỉ dùng được cho instance receivers?  
**Đáp án:** Không. Static method có leading reference parameter cũng bind được.

**Câu 7.** `(String,int)String` bind `"ORD-"` thành type gì?  
**Đáp án:** `(int)String`.

**Câu 8.** Có thể tiếp tục `bindTo(Integer.valueOf(7))` trên `(int)String` không?  
**Đáp án:** Không; `IllegalArgumentException` do leading primitive.

**Câu 9.** Muốn cố định `int` 7, dùng gì?  
**Đáp án:** `MethodHandles.insertArguments(handle,0,7)` nếu int ở index 0; nếu int ở index 1 dùng pos=1.

**Câu 10.** Static handle `(int,String)String` muốn cố định `String` ở index 1?  
**Đáp án:** `insertArguments(handle,1,"!")`.

**Câu 11.** Có thể chain `bindTo` không?  
**Đáp án:** Có, khi mỗi lần tham số đứng đầu còn lại đều là reference.

**Câu 12.** Sai kiểu reference lúc bind gây lỗi gì?  
**Đáp án:** `ClassCastException`.

**Câu 13.** Handle không có tham số, gọi `bindTo`?  
**Đáp án:** `IllegalArgumentException`.

**Câu 14.** Bind null vào static method nhận `String` có được không?  
**Đáp án:** Có. Target tự quyết định xử lý null lúc invoke.

**Câu 15.** Bind null thành receiver của `String.toUpperCase` gây lỗi lúc nào?  
**Đáp án:** NPE khi invoke vì receiver null, không bắt buộc ngay lúc bind.

**Câu 16.** Tại sao `Object x = (Object) handle.invokeExact(7)` có thể sai dù target trả String?  
**Đáp án:** Call site yêu cầu return type `Object` nhưng handle type trả `String` chính xác; ném `WrongMethodTypeException`.

**Câu 17.** `bindTo` có tạo bản sao `StringBuilder` receiver không?  
**Đáp án:** Không, nó giữ reference tới cùng builder.

**Câu 18.** Bound handle tới mutable receiver có tự thread-safe không?  
**Đáp án:** Không. Thread-safety theo target/receiver, không do `bindTo`.

**Câu 19.** Có rủi ro memory khi cache bound handles không?  
**Đáp án:** Có. Adapter có thể giữ reference tới những receiver/config objects lâu hơn dự kiến.

**Câu 20.** `bindTo` có bỏ qua access checks trên private method không?  
**Đáp án:** Không. `Lookup` phải đủ quyền để tạo handle; đừng phát tán handle nhạy cảm.

**Câu 21.** `bindTo` có đổi return type của method không?  
**Đáp án:** Không. Chỉ bỏ leading reference parameter, giữ return type.

**Câu 22.** `insertArguments` có mutate original target không?  
**Đáp án:** Không. Nó trả adapter mới, tương tự bindTo.

**Câu 23.** Nên chọn lambda hay bound MethodHandle cho callback đơn giản?  
**Đáp án:** Ưu tiên giải pháp rõ ràng; MethodHandle phù hợp khi cần dynamic handles/typed combinators, không phải tự động nhanh hơn.

**Câu 24.** Dựa vào `MethodHandle.toString()` để parse type tự động có tốt không?  
**Đáp án:** Không. Dùng `type()`/`MethodType.parameterType` thay vì parse chuỗi debug.

## 14. Checklist trước khi dùng `bindTo`

- [ ] Xác nhận có đúng `MethodHandle` cần dùng từ `Lookup` phù hợp.
- [ ] Biết handle gốc là static hay instance; receiver hiện ra trong `MethodType` của instance handle.
- [ ] In/kiểm tra `handle.type()` nếu tạo adapters động.
- [ ] Chỉ dùng `bindTo` khi leading parameter là **reference**.
- [ ] Giá trị bind phải convert/cast được tới reference parameter type.
- [ ] Khi cần bind primitive hoặc param không ở index 0, dùng `insertArguments`.
- [ ] Không giả định `bindTo(Object)` tự unbox leading primitive.
- [ ] Không gọi `bindTo` với handle zero-arity.
- [ ] Phân biệt lỗi bind-time `IllegalArgumentException`/`ClassCastException` với invoke-time failures.
- [ ] Với nullable receiver/argument, hiểu target có thể ném NPE.
- [ ] Biết chính xác type sau mỗi lần bind; target original không đổi.
- [ ] `invokeExact` phải khớp static argument và return types.
- [ ] Nếu dùng `invoke`/`asType`, hiểu các conversions và limits.
- [ ] Không bắt `Throwable` rộng rồi nuốt lỗi nghiệp vụ trong production.
- [ ] Bind nhiều refs liên tiếp chỉ khi chữ ký sau mỗi bước còn leading reference.
- [ ] Với object mutable, không coi bind là copy/freeze.
- [ ] Nếu share bound handle giữa threads, target phải đáp ứng thread-safety.
- [ ] Quản lý vòng đời/caches để không giữ references lâu ngoài ý muốn.
- [ ] Không tiết lộ handles gắn privileged receiver hoặc secrets cho untrusted code.
- [ ] Lookup phải thỏa Java visibility/module access; không dùng JDK-internal hacks.
- [ ] Không biến lambda đơn giản thành method handle nếu không có nhu cầu dynamic dispatch.
- [ ] Kiểm thử stdout và exception bằng Java 17+/21 trước khi đưa vào pipeline.
- [ ] Chỉ dựa vào API public còn được hỗ trợ, không dùng hướng dẫn legacy.

## 15. Tài liệu chính thức còn áp dụng

- [Oracle Java SE 21 — MethodHandle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandle.html): `bindTo(Object)`, `invoke`, `invokeExact`, `type()`, exception rules, immutable adapter.
- [Oracle Java SE 21 — MethodHandles](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandles.html): `lookup()`, `insertArguments`, `filterArguments`, `permuteArguments`, `dropArguments` và adapters.
- [Oracle Java SE 21 — MethodHandles.Lookup](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): `findVirtual`, `findStatic`, access checks và capabilities.
- [Oracle Java SE 21 — MethodType](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodType.html): typed descriptor, parameter/return types và `methodType` factory.
- [Oracle Java SE 21 — WrongMethodTypeException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/WrongMethodTypeException.html): lỗi mismatch ở method-handle call site.
- [Oracle Java SE 21 — String](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html): `substring` và `toUpperCase` được dùng trong demo.
- [Oracle Java SE 21 — StringBuilder](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/StringBuilder.html): mutable receiver và `append(String)`.

**Kết luận:** `MethodHandle.bindTo(Object)` là **partial application cho leading reference argument**, thường chính là receiver của instance method, nhưng cũng có thể là tham số đầu của static method. Nó tạo adapter immutable, bớt một parameter, giữ lại target và return type. **Không dùng `bindTo` cho primitive hay nonleading parameter**: hãy dùng `MethodHandles.insertArguments`. Luôn kiểm tra `MethodType` khi dùng `invokeExact`, phân biệt lỗi bind-time và invoke-time, quản lý lifetime/thread-safety của object đã bind và dùng API Java còn được hỗ trợ hiện nay.
