# 7.1 Chữ ký đa hình và descriptor mà trình biên dịch ghi tại nơi gọi

**Module:** Java Advance - dynamic-runtime  
**Nhóm kiến thức:** 7. Gọi method handle

## Mục tiêu

Khi gọi một `MethodHandle`, Java không đơn giản tìm một overload mang đúng số tham số như lời gọi phương thức thông thường. Hai phương thức `MethodHandle.invokeExact` và `MethodHandle.invoke` có cơ chế **signature polymorphism** (chữ ký đa hình), làm cho **kiểu tĩnh của các biểu thức đối số** và **ngữ cảnh kiểu trả về** tác động trực tiếp tới *method descriptor* được trình biên dịch ghi trong bytecode ở từng nơi gọi.

Sau bài này, bạn có thể:

1. Giải thích signature polymorphic method là gì, tại sao `invokeExact`/`invoke` khác phương thức varargs bình thường, và phân biệt nó với overload, generic và `invokedynamic`.
2. Phân biệt **`MethodHandle.type()`** (kiểu mà handle đang có) với **descriptor tại call site** (do `javac` quyết định từ mã nguồn của một lời gọi cụ thể).
3. Đọc các descriptor `(Ljava/lang/String;)Ljava/lang/String;`, `(Ljava/lang/Object;)Ljava/lang/String;`, `(Ljava/lang/String;)V` và liên hệ chúng với source.
4. Dự đoán `invokeExact` thành công hay ném `WrongMethodTypeException`; giải thích tại sao một thay đổi về cast, khai báo biến hoặc cách dùng kết quả có thể đổi descriptor.
5. Hiểu `invoke` dùng chuyển đổi kiểu giống `asType` khi phù hợp; biết giới hạn của chuyển đổi này và khi nào cần `asType` một cách tường minh.
6. Biên dịch Java 17+, chạy ví dụ và dùng `javap` tự kiểm chứng các lời gọi `invokevirtual`.

## 1. Ba thứ phải tách riêng

Trước khi nói đến descriptor, hãy tách ba khái niệm thường bị trộn lẫn.

| Khái niệm | Nó mô tả điều gì? | Ví dụ |
| --- | --- | --- |
| **Phương thức đích** | Method/constructor/field operation mà một handle được tạo để biểu diễn | `static String decorate(String text)` |
| **Kiểu của handle** (`MethodHandle.type()`) | Thứ tự, kiểu đối số và kiểu trả về mà *handle hiện tại* chấp nhận | `(String)String` |
| **Descriptor của lời gọi** | Chữ ký ký hiệu được `javac` ghi ở instruction gọi `invokeExact`/`invoke` cụ thể | `(Ljava/lang/String;)Ljava/lang/Object;` |

Một handle có thể mang kiểu `(String)String` nhưng hai dòng mã nguồn sau yêu cầu **hai descriptor khác nhau**:

~~~java
String text = (String) handle.invokeExact("java");
Object value = handle.invokeExact("java");
~~~

Dòng thứ nhất yêu cầu `(String)String`; dòng thứ hai yêu cầu `(String)Object`. Nếu `handle.type()` đúng là `(String)String`, dòng đầu có thể chạy, còn dòng sau ném `WrongMethodTypeException`. Điều này xảy ra **dù đối tượng String trả về nếu lời gọi chạy thành công vẫn là một String ở runtime**. Ở `invokeExact`, kiểu *khai báo trong descriptor* phải khớp, không chỉ là việc giá trị trả về có thể gán cho `Object`.

Hai dòng trên **chỉ minh họa khi biến `handle` đã được khai báo/tạo**; chương trình chạy hoàn chỉnh nằm ở mục 5.

## 2. Signature polymorphic method thực chất là gì?

### 2.1. Vì sao một phương thức trông giống `Object...` lại chấp nhận nhiều chữ ký?

Trong Java SE 17, `MethodHandle` cung cấp các phương thức public native varargs với dạng khai báo tương tự:

~~~java
public final native Object invokeExact(Object... args) throws Throwable;
public final native Object invoke(Object... args) throws Throwable;
~~~

Đây là **hình dạng khai báo mang tính minh họa** của API, không phải mã để tự triển khai. Theo quy tắc ngôn ngữ Java, các phương thức native varargs thuộc `MethodHandle` (và các access mode method tương ứng trên `VarHandle`) có cơ chế *signature polymorphic*. Trình biên dịch cho phép gọi chúng với các danh sách đối số có kiểu khác nhau; tại nơi gọi, nó tạo một **descriptor chuyên biệt**.

Vì vậy:

~~~java
(String) handle.invokeExact("java")
~~~

không được hiểu thành “Java gom `"java"` vào `Object[]` rồi gọi một method nhận mảng”. Thông thường, không có bước đóng gói `Object[]` như ở varargs Java bình thường. Thay vào đó, bytecode có thể chứa `invokevirtual` tham chiếu đến:

~~~text
java/lang/invoke/MethodHandle.invokeExact:(Ljava/lang/String;)Ljava/lang/String;
~~~

JVM có quy tắc phân giải và thực thi đặc biệt cho các lời gọi signature polymorphic. Nó không yêu cầu `MethodHandle` thật sự khai báo một overload Java riêng cho từng descriptor do compiler sinh ra.

**Phân biệt:** không phải method bất kỳ có `Object...` cũng nhận được xử lý đặc biệt này. Một method do bạn tự viết tên `invokeExact` với `Object...` vẫn là phương thức varargs thông thường. Không thể tự tạo signature polymorphic method bằng cách chỉ thêm `native` hoặc dùng annotation nội bộ không được hỗ trợ.

### 2.2. Khác gì overload, generic và `invokedynamic`?

- **Overload:** compiler chọn một trong nhiều khai báo thực tế cùng tên nhưng khác parameter types, theo quy tắc overload resolution.
- **Generic:** compiler kiểm tra type parameters, inference và erasure; các runtime method descriptors thường liên quan chữ ký sau erasure.
- **Signature polymorphism:** khai báo đặc biệt có thể xuất hiện tại **nhiều descriptor khác nhau ở call site**; JVM hiểu cách phân giải dù không có từng overload tương ứng.
- **`invokedynamic`:** instruction bytecode riêng dùng bootstrap method để liên kết dynamic call site. Lời gọi `handle.invokeExact(...)` thông thường được biên dịch bằng **`invokevirtual`**, không phải `invokedynamic`. Một bootstrap của `invokedynamic` *có thể* tạo/dùng method handle, nhưng đó là cơ chế liên kết khác.

Nói “method handle là dynamic” không đồng nghĩa mọi nơi gọi method handle đều phát sinh `invokedynamic`.

## 3. `javac` quyết định descriptor như thế nào?

Theo JLS `15.12.3`, với method invocation signature polymorphic, trình biên dịch xác định **kiểu tham số lúc biên dịch** từ chính kiểu của **các biểu thức đối số**, không thực hiện bộ chuyển đổi method invocation thông thường để ép chúng về `Object[]`.

Với phương thức trả kiểu `Object` như `invokeExact`/`invoke`, **kiểu trả về của lời gọi tại compile time** được xác định bởi ngữ cảnh:

1. Nếu lời gọi là **operand trực tiếp của một phép cast**, compiler lấy **erasure của kiểu cast** làm kiểu trả về của lời gọi.
2. Nếu lời gọi được dùng như **expression statement** (kết quả không dùng), kiểu trả về là `void`.
3. Trong trường hợp còn lại, kiểu trả về là `Object`.

Đó là lý do **cast phía ngoài lời gọi** rất quan trọng:

| Biểu thức Java | Parameter type tại call site | Return type tại call site | Descriptor JVM |
| --- | --- | --- | --- |
| `(String) h.invokeExact("java")` | `String` | `String` | `(Ljava/lang/String;)Ljava/lang/String;` |
| `Object x = h.invokeExact("java")` | `String` | `Object` | `(Ljava/lang/String;)Ljava/lang/Object;` |
| `(String) h.invokeExact((Object) "java")` | `Object` | `String` | `(Ljava/lang/Object;)Ljava/lang/String;` |
| `h.invokeExact("java");` | `String` | `void` | `(Ljava/lang/String;)V` |
| `Object x = h.invoke("java")` | `String` | `Object` | `(Ljava/lang/String;)Ljava/lang/Object;` |

Các dòng trong bảng là **biểu thức minh họa** với biến handle `h` có sẵn. Có ba nhận xét quan trọng:

- `"java"` có **kiểu biểu thức `String`**. Ép `(Object) "java"` đổi kiểu biểu thức thành `Object` mặc dù runtime object vẫn là chuỗi ký tự giống hệt.
- Gán giá trị cho một biến `Object` **không tự làm** `invokeExact` chuyển kết quả `String` thành `Object`; compiler đã ghi return descriptor theo quy tắc ở trên.
- `h.invokeExact("java");` bỏ kết quả, khiến return descriptor là `V` (void). Handle có return type `String` sẽ không khớp descriptor đó nếu dùng `invokeExact`.

**Một bẫy thường gặp:** viết `String s = h.invokeExact("java");` không giống `String s = (String) h.invokeExact("java");`. Với lời gọi không có cast trực tiếp, kiểu static của expression là `Object` nên phép gán trực tiếp sang `String` không hợp lệ. Cần cast để chọn kiểu trả về đúng như ý định.

### 3.1. Cách đọc JVM method descriptor

Một *method descriptor* có cấu trúc:

~~~text
(kiểu_tham_số_1 kiểu_tham_số_2 ...)kiểu_trả_về
~~~

Một số ký hiệu phổ biến:

| Ký hiệu | Kiểu Java |
| --- | --- |
| `I` | `int` |
| `J` | `long` |
| `Z` | `boolean` |
| `V` | `void` (chỉ ở vị trí trả về của method descriptor) |
| `Ljava/lang/String;` | `java.lang.String` |
| `Ljava/lang/Object;` | `java.lang.Object` |
| `[I` | `int[]` |
| `[Ljava/lang/String;` | `String[]` |

Ví dụ:

~~~text
(Ljava/lang/String;)Ljava/lang/String;    // String -> String
(Ljava/lang/Object;)Ljava/lang/String;    // Object -> String
(II)I                                    // (int, int) -> int
()V                                      // () -> void
~~~

Descriptor ở `invokevirtual` **không liệt kê receiver `MethodHandle` bên trong dấu ngoặc**; receiver nằm riêng trên operand stack của instruction. Với `MethodHandle.findVirtual` trỏ đến một *instance method*, `MethodHandle.type()` lại có thể có đối tượng receiver **của method đích** làm tham số đầu tiên. Đó là hai khái niệm receiver khác nhau: receiver của instruction gọi handle và receiver của target method.

### 3.2. Kiểu tĩnh quan trọng hơn kiểu của object lúc chạy

Xét:

~~~java
Object input = "java";
String output = (String) handle.invokeExact(input);
~~~

Dù `input` hiện đang chứa một `String`, biểu thức `input` có kiểu **`Object`** ở compile time. Vì vậy descriptor là `(Object)String`, không phải `(String)String`. Chỉ gán lại vào một biến String hoặc cast đối số sang String khi hợp đồng cho phép mới thay đổi descriptor:

~~~java
String typed = (String) input;
String output = (String) handle.invokeExact(typed);
~~~

Cả hai đoạn là **minh họa riêng**, không đặt cạnh nhau trong cùng block Java vì trùng tên biến. Trường hợp đầu không phù hợp với handle `(String)String` và ném `WrongMethodTypeException`. Trường hợp sau có descriptor phù hợp; việc cast `input` sang String trước đó vẫn có thể ném `ClassCastException` nếu object không thực sự là String.

## 4. Runtime kiểm tra descriptor ra sao?

### 4.1. `MethodHandle.type()` là hợp đồng runtime của handle

Một handle có `type() == MethodType.methodType(String.class, String.class)` nhận một đối số `String` và trả kết quả kiểu `String`. Cách in dễ đọc của `type()` là:

~~~text
(String)String
~~~

JVM có quy tắc phân giải symbol đặc biệt cho `MethodHandle.invokeExact` và `invoke`. Tại thời điểm chạy instruction, nó xét **method type được suy ra từ descriptor ký hiệu tại nơi gọi** và so với type của handle hiện tại.

**Với `invokeExact`:**

- Kiểu ở nơi gọi phải **bằng chính xác** `MethodHandle.type()` sau khi resolve các kiểu ký hiệu.
- So sánh cả **thứ tự tham số, từng kiểu tham số và kiểu trả về**.
- Không tự boxing/unboxing, widening primitive hoặc cast kiểu tham chiếu để bù cho mismatch trong chữ ký.
- Khi không khớp, ném `WrongMethodTypeException`. Khi khớp, handle tiến hành gọi mục tiêu; lỗi phát sinh bên trong target vẫn có thể được truyền ra.

**Với `invoke`:**

- Nếu descriptor trùng với kiểu handle, lời gọi hành xử tương tự `invokeExact`.
- Nếu không trùng, JVM thử một chuyển đổi tương đương `handle.asType(callSiteType)`; nếu chuyển đổi kiểu được hỗ trợ, nó áp dụng adapter phù hợp trước/sau khi gọi target.
- Các chuyển đổi có thể bao gồm **reference cast**, **boxing/unboxing** và một số **primitive widening** theo quy tắc của `asType`. Đây **không phải** cơ chế ép kiểu tùy ý: chuyển đổi không thể lập được có thể ném `WrongMethodTypeException`; cast thực tế không thành công có thể ném `ClassCastException`.
- `invoke` **không biến đổi vĩnh viễn** kiểu của biến handle gốc. Không nên suy ra nó luôn rẻ bằng `invokeExact` hoặc luôn chậm hơn: cần đo ngữ cảnh thực tế.

### 4.2. Chọn cách gọi từ hợp đồng sẵn có

| Nhu cầu | Cách tiếp cận |
| --- | --- |
| Biết chính xác `MethodType` và muốn gọi với signature đó | Dùng `invokeExact` với kiểu đối số **và kiểu kết quả** khớp |
| Muốn JVM thích nghi giữa hai kiểu có chuyển đổi `asType` hợp lệ | Dùng `invoke` và xác minh conversion semantics |
| Muốn tạo một handle có `type()` mới, rõ ràng, rồi gọi exact | `MethodHandle.asType(...)`, sau đó `invokeExact` với descriptor mới |
| Muốn gọi với danh sách `Object` thu thập động từ metadata | Cân nhắc `invokeWithArguments` hoặc adapter phù hợp, hiểu thêm overhead và conversion rules |
| Muốn truyền một mảng làm **một** tham số | Kiểm tra descriptor dạng array, `asFixedArity()` hoặc adapter liên quan khi cần; không ngầm coi mảng thành varargs |
| Muốn chuyển từ receiver instance sang handle gọi method | `findVirtual` tạo handle có receiver target là một phần `MethodType` |

`invokeWithArguments` là một API khác `invoke`/`invokeExact`; nó nhận danh sách Object theo cách thông thường hơn, thuận tiện khi số/kiểu argument chỉ được biết động nhưng không nên nhầm nó với cú pháp signature polymorphic.

## 5. Thực hành Java 17+: cùng một handle, nhiều call-site descriptor

Chương trình sử dụng **một handle gốc** cho phương thức static `decorate(String)`, có type `(String)String`. Các lời gọi đầu tiên thành công; ba trường hợp `invokeExact` sau cố ý tạo descriptor sai để quan sát `WrongMethodTypeException`; cuối cùng `asType` tạo handle khác phù hợp chữ ký `(Object)Object`.

**Tệp:** `SignaturePolymorphicDemo.java`

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;
import java.util.Locale;

public class SignaturePolymorphicDemo {
    public static String decorate(String text) {
        return "[" + text.toUpperCase(Locale.ROOT) + "]";
    }

    public static void main(String[] args) throws Throwable {
        MethodHandle handle = MethodHandles.lookup().findStatic(
                SignaturePolymorphicDemo.class,
                "decorate",
                MethodType.methodType(String.class, String.class));

        System.out.println("handleType=" + handle.type());

        String exact = (String) handle.invokeExact("java");
        System.out.println("exact=" + exact);

        Object flexibleResult = handle.invoke("jvm");
        System.out.println("invokeResult=" + flexibleResult);

        String flexibleArgument = (String) handle.invoke((Object) "api");
        System.out.println("invokeArgument=" + flexibleArgument);

        try {
            Object ignored = handle.invokeExact("java");
            System.out.println("unexpected=" + ignored);
        } catch (WrongMethodTypeException expected) {
            System.out.println("exactReturnMismatch");
        }

        try {
            String ignored = (String) handle.invokeExact((Object) "java");
            System.out.println("unexpected=" + ignored);
        } catch (WrongMethodTypeException expected) {
            System.out.println("exactParameterMismatch");
        }

        try {
            handle.invokeExact("java");
            System.out.println("unexpected");
        } catch (WrongMethodTypeException expected) {
            System.out.println("exactVoidMismatch");
        }

        MethodHandle generic = handle.asType(
                MethodType.methodType(Object.class, Object.class));
        Object exactAfterAdapt = (Object) generic.invokeExact((Object) "module");
        System.out.println("adaptedExact=" + exactAfterAdapt);
    }
}
~~~

Lưu mã nguồn theo đúng tên file `SignaturePolymorphicDemo.java`. Từ thư mục chứa file, dùng JDK 17 trở lên:

~~~bash
javac --release 17 -d out SignaturePolymorphicDemo.java
java -cp out SignaturePolymorphicDemo
~~~

**Stdout chính xác của chương trình đã kiểm chứng:**

~~~text
handleType=(String)String
exact=[JAVA]
invokeResult=[JVM]
invokeArgument=[API]
exactReturnMismatch
exactParameterMismatch
exactVoidMismatch
adaptedExact=[MODULE]
~~~

### 5.1. Diễn giải từng lời gọi

| Dòng quan trọng | Descriptor tại nơi gọi | Tác động |
| --- | --- | --- |
| `(String) handle.invokeExact("java")` | `(String)String` | Trùng `handle.type()`; gọi thành công |
| `handle.invoke("jvm")` gán cho `Object` | `(String)Object` | `invoke` có thể thích nghi return `String` thành `Object` |
| `(String) handle.invoke((Object) "api")` | `(Object)String` | `invoke` có thể ép reference Object chứa String về String |
| `Object ignored = handle.invokeExact("java")` | `(String)Object` | `invokeExact` thất bại ở **return type** |
| `(String) handle.invokeExact((Object) "java")` | `(Object)String` | `invokeExact` thất bại ở **parameter type** |
| `handle.invokeExact("java");` | `(String)void` | `invokeExact` thất bại do **return void** |
| `(Object) generic.invokeExact((Object) "module")` | `(Object)Object` | Trùng **`generic.type()`** sau `asType`; gọi thành công |

Điểm cần nhớ: hai handle `handle` và `generic` đều chuyển đến hành vi `decorate`, nhưng có **`MethodType` khác nhau**. `asType` xây adapter với type mới; nó không thay đổi type của handle gốc. Khi code gọi exact trên `generic`, kiểu static của cả đối số và kết quả đều là `Object` như adapter yêu cầu.

### 5.2. Quan sát bytecode bằng `javap`

Sau khi biên dịch đúng chương trình trên:

~~~bash
javap -c -p -classpath out SignaturePolymorphicDemo
~~~

Trong `main`, tìm các instruction `invokevirtual` liên quan `MethodHandle.invokeExact` và `MethodHandle.invoke`. Dưới đây là **các phần comment descriptor tiêu biểu**, bỏ bytecode offset và chỉ số constant-pool vì chúng có thể thay đổi khi sửa mã nguồn hoặc chọn phiên bản compiler khác:

~~~text
Method java/lang/invoke/MethodHandle.invokeExact:(Ljava/lang/String;)Ljava/lang/String;
Method java/lang/invoke/MethodHandle.invoke:(Ljava/lang/String;)Ljava/lang/Object;
Method java/lang/invoke/MethodHandle.invoke:(Ljava/lang/Object;)Ljava/lang/String;
Method java/lang/invoke/MethodHandle.invokeExact:(Ljava/lang/String;)Ljava/lang/Object;
Method java/lang/invoke/MethodHandle.invokeExact:(Ljava/lang/Object;)Ljava/lang/String;
Method java/lang/invoke/MethodHandle.invokeExact:(Ljava/lang/String;)V
Method java/lang/invoke/MethodHandle.invokeExact:(Ljava/lang/Object;)Ljava/lang/Object;
~~~

Các descriptor này đã được xác nhận bằng `javap -c -p` cho source của ví dụ. `invokevirtual` đứng trước mỗi comment thực tế; tập descriptor xuất hiện tương ứng các dòng ở bảng. **Mỗi instruction** tham chiếu đúng descriptor do `javac` suy ra từ biểu thức nguồn, không lấy lại descriptor đó bằng Reflection tại runtime.

Nếu muốn nhìn cả constant pool và method references, dùng:

~~~bash
javap -v -p -classpath out SignaturePolymorphicDemo
~~~

Tìm `Methodref` tương ứng `java/lang/invoke/MethodHandle.invokeExact` hoặc `invoke`. Cách `javap` in một số line, offset hay pool index là chi tiết của artifact, nên **không so khớp máy móc số `#70`, `#76`...** giữa các lần build.

## 6. Vì sao JVM phân giải được descriptor không giống khai báo?

Trong `MethodHandle`, khai báo Java nhìn giống `Object invokeExact(Object... args)`. Một lời gọi `invokeExact:(Ljava/lang/String;)Ljava/lang/String;` không có một overload được khai báo bình thường tương ứng. Nếu áp quy tắc resolution của các method Java thông thường mà bỏ ngoại lệ signature polymorphic, nó trông như “method không tồn tại”.

JVM Specification (`5.4.3.3` và `6.5 invokevirtual`) xử lý riêng signature polymorphic method:

1. **Symbolic reference** trong constant pool giữ class, tên method và descriptor do compiler phát hành.
2. Khi JVM resolution/verification, nó biết method `invokeExact`/`invoke` của `MethodHandle` là signature polymorphic; không đòi có một khai báo method mang chính xác descriptor đa dạng ấy.
3. JVM resolve các kiểu được nhắc trong descriptor, kiểm tra cấu trúc phù hợp, rồi tại invocation **thu được `MethodType` tương ứng descriptor**.
4. Với `invokeExact`, JVM yêu cầu `MethodType` đó trùng `handle.type()`; với `invoke`, nó kiểm tra phép thích nghi kiểu theo `asType`.
5. Handle hợp lệ chuyển điều khiển đến target hoặc adapter; exception của target vẫn được truyền theo cơ chế của method handle.

Do đó lỗi `WrongMethodTypeException` trong ví dụ **không có nghĩa** class `MethodHandle` thiếu method tên `invokeExact` hoặc JVM không thể resolve symbol. Call site đã được link theo cơ chế đặc biệt; lỗi phát sinh khi **signature thực tế của handle không thỏa yêu cầu nơi gọi**.

Phân biệt rõ hai dạng “liên kết”:

- **Liên kết symbolic method reference**: JVM nhận ra một lệnh gọi signature polymorphic và descriptor của nó là hợp lệ.
- **Kiểm tra tương thích handle tại invocation**: JVM áp yêu cầu exact hoặc adaptable lên `MethodHandle` nhận được ở runtime.

JVM có thể tối ưu hóa các đường gọi này, nhưng không được giả định một chi phí cố định cho mọi version/runtime.

## 7. Những hệ quả thực tế khi viết API động

### 7.1. Một sửa đổi ở source có thể đổi descriptor mà không đổi giá trị runtime

Ví dụ:

~~~java
String s = "java";
Object o = s;
String a = (String) handle.invokeExact(s); // (String)String
String b = (String) handle.invokeExact(o); // (Object)String
~~~

Đoạn là **minh họa trong scope có handle kiểu `(String)String`**, nên dòng `a` có thể chạy còn dòng `b` ném `WrongMethodTypeException`. Việc `o` vẫn trỏ đến cùng String không làm hai descriptor giống nhau. Muốn exact-call qua biến `Object`, hãy kiểm tra/cast kiểu theo contract trước, hoặc dùng handle đã thích nghi.

### 7.2. Tương tác với generic và erasure

Khi một phương thức bao generic chứa lời gọi `invokeExact`, kiểu tĩnh có thể được **erased** tại bytecode. Giá trị ở runtime có vẻ đúng type nhưng descriptor không khớp với handle cụ thể. Ví dụ, một biến đối số khai báo kiểu `T` mà `T` bị erasure thành `Object` có thể dẫn tới descriptor dùng `Object`. Đừng chỉ nhìn giá trị trong debugger; luôn xét kiểu tĩnh/cast của biểu thức và kiểm tra bytecode.

Nên kiểm tra `handle.type()`, dùng adapter tại ranh giới API, hoặc thiết kế một điểm gọi có signature tĩnh biết trước. Cố gắng “ép đại một cast” ở ngoài biểu thức mà chưa biết return/argument contract có thể dẫn đến lỗi sớm hoặc khó hiểu hơn.

### 7.3. Signature polymorphic **không** xóa bỏ quy tắc truy cập khi tạo handle

Việc tạo `MethodHandle` bằng `Lookup.findStatic`, `findVirtual`, `findConstructor` v.v. vẫn phải tuân theo quyền truy cập Java/module. `invokeExact` không cho phép vượt quyền private method; nó chỉ mô tả cách gọi một handle **đã được cấp và tạo hợp lệ**. Kết quả lỗi liên quan `IllegalAccessException` lúc `Lookup` tạo handle khác về gốc rễ so với `WrongMethodTypeException` lúc gọi sai descriptor.

### 7.4. Sai kiểu của giá trị và sai signature là hai lỗi khác

- `WrongMethodTypeException`: call-site descriptor sai đối với `invokeExact`, hoặc `invoke` không thể tạo adapter theo `asType`.
- `ClassCastException`: phép tham chiếu cast/adaptation hợp lệ về mặt chữ ký nhưng giá trị runtime không phù hợp, chẳng hạn ép một `Integer` đang nằm trong `Object` sang `String` để target nhận.
- `NullPointerException`: có thể xảy ra nếu receiver `MethodHandle` là `null` hoặc target tự dereference null.
- Exception của **target**: một handle có type phù hợp vẫn có thể gọi logic nghiệp vụ ném exception. Vì `invokeExact`/`invoke` khai báo `throws Throwable`, mã nguồn gọi chúng phải xử lý/công bố ngoại lệ phù hợp; demo chọn `main throws Throwable` để minh họa tập trung.

## 8. Lỗi thường gặp và cách debug

| Hiện tượng | Nguyên nhân có thể | Cách xác minh |
| --- | --- | --- |
| `invokeExact` báo `WrongMethodTypeException` dù argument “đúng” | Tên/kiểu tĩnh biến đối số khác loại mà handle nhận | In `handle.type()`; xem cast và descriptor ở `javap` |
| `invokeExact` báo sai return type | Không cast trực tiếp lời gọi, cast sai kiểu hoặc bỏ kết quả | Kiểm tra return type ở descriptor: `Ljava/lang/Object;`, `Ljava/lang/String;` hay `V` |
| `invoke` làm việc còn `invokeExact` lỗi | `invoke` đã thích nghi kiểu nhờ cơ chế `asType` | So sánh `MethodType` gốc và call site; thử `asType` tường minh |
| `invoke` báo `ClassCastException` | Runtime object không phù hợp với phép cast của adapter | Quan sát type thực của argument, kiểm tra boundary conversion |
| `invoke` báo `WrongMethodTypeException` | `asType` không hỗ trợ chuyển đổi mong muốn | Đối chiếu API `asType` về primitive/reference/boxing |
| Cố dùng `String x = mh.invokeExact(...)` gây compile error | Khi không có cast trực tiếp, return expression là `Object` | Viết `(String) mh.invokeExact(...)` sau khi xác minh handle return type |
| `javap` hiển thị `invokevirtual` thay vì `invokedynamic` | Đây là bytecode đúng của `MethodHandle.invokeExact`/`invoke` | Phân biệt signature-polymorphic invokevirtual với bootstrap-based invokedynamic |
| Xem Reflection thấy `invokeExact(Object[])` | Reflection biểu diễn khai báo placeholder, không mô tả mọi descriptor call site | Dùng `javap` hoặc `MethodHandle.type()` để kiểm tra đúng tầng |
| Thấy `NoSuchMethodException` khi tạo handle | `findStatic`/`findVirtual` không tìm thấy đúng method/signature | Kiểm tra class, tên, `MethodType` và quyền truy cập độc lập với call site |

**Quy trình chẩn đoán ngắn:**

1. In `handle.type()` ngay trước lời gọi lỗi; phân biệt handle gốc với handle adapter.
2. Xác định **kiểu tĩnh** của từng đối số trong source, bao gồm `(Object)`, primitive boxing và generic erasure.
3. Xem lời gọi có cast **trực tiếp** đến kiểu trả về nào, hay kết quả bị bỏ, hay dùng dưới ngữ cảnh khác.
4. Dùng `javap -c -p` trên **class file đang thực sự chạy**, tìm đúng instruction `invokevirtual MethodHandle.invokeExact/invoke:...`.
5. So descriptor với `handle.type()`: exact yêu cầu trùng; inexact đòi hỏi chuyển đổi `asType` hợp lệ.
6. Nếu descriptor khớp nhưng vẫn lỗi, xem giá trị runtime, access/target exception, class loader/module và nguồn build.

**Lưu ý khi tối ưu:** tránh biến API thành `Object...` khắp nơi chỉ để né sai kiểu; thay vào đó, đặt contract type rõ ở ranh giới động, tạo adapter có mục đích và cache khi có căn cứ. Những quyết định hiệu năng phải có đo đạc đáng tin.

## 9. Bài tập tự kiểm tra

**Câu 1 — Dự đoán descriptor.** Giả sử `h.type() == (int)long` (một đối số int, trả long). Hãy dự đoán descriptor cho:

~~~java
long a = (long) h.invokeExact(5);
Object b = h.invokeExact(5);
h.invokeExact(5);
~~~

Đáp án: lần lượt `(I)J`, `(I)Ljava/lang/Object;` và `(I)V`. Với handle `(int)long`, chỉ biểu thức đầu có kiểu exact phù hợp. Đây là **ba biểu thức minh họa**, không phải chương trình độc lập.

**Câu 2 — Đổi khai báo biến.** Thay `"java"` trong chương trình chính bằng `Object input = "java"` rồi gọi `(String) handle.invokeExact(input)`. Hãy dự đoán lỗi và giải thích vì sao kiểu object runtime không cứu được descriptor.

**Câu 3 — Xem bytecode.** Tìm dòng `invokeExact:(Ljava/lang/String;)V` trong output `javap`. Chỉ ra câu lệnh Java tương ứng và giải thích vì sao bỏ return value đổi call-site type.

**Câu 4 — Thử adapter.** So sánh `(String) handle.invoke((Object) "api")` với `(Object) generic.invokeExact((Object) "api")`: điều gì chuyển đổi ở call site, điều gì được thay đổi trước trong handle adapter?

**Câu 5 — Phân biệt với `invokedynamic`.** Giải thích tại sao một lời gọi `handle.invokeExact("java")` được ghi bằng `invokevirtual` mặc dù phương thức có tên/hành vi “dynamic”. Nếu gặp `invokedynamic` trong một class dùng lambda, có thể kết luận nó chính là lệnh gọi `invokeExact` không?

**Câu 6 — Tính chất của return cast.** Vì sao:

~~~java
String s = (String) h.invokeExact("java");
~~~

khác:

~~~java
Object o = h.invokeExact("java");
String s = (String) o;
~~~

Ở đoạn sau, cast xảy ra **sau lời gọi** nên không sửa return descriptor của call site `invokeExact`. Nếu handle trả `String`, đoạn sau ném `WrongMethodTypeException` ngay trước khi có giá trị `o`. Hai đoạn là những ví dụ độc lập.

## 10. Ghi nhớ

- **Signature polymorphism** cho `MethodHandle.invokeExact`/`invoke` làm lời gọi phát sinh descriptor từ **kiểu biểu thức đối số và ngữ cảnh kết quả**, không từ một chữ ký `Object[]` cố định.
- `javac` ghi các method references đến `MethodHandle.invokeExact`/`invoke` kèm **descriptor cụ thể**; lệnh gọi Java này dùng **`invokevirtual`**.
- **`handle.type()`** là kiểu runtime của handle; **descriptor** là yêu cầu kiểu do call site mang theo.
- **`invokeExact`** yêu cầu hai kiểu bằng nhau, bao gồm cả kiểu trả về; sai lệch tạo `WrongMethodTypeException`.
- **`invoke`** có thể thực hiện thích nghi `asType`, nhưng không chấp nhận mọi dạng chuyển đổi.
- Cast ở **đối số** thay kiểu parameter của descriptor; cast **trực tiếp vào lời gọi** quyết định kiểu return; dùng lời gọi như một statement làm return descriptor thành `V`.
- Khi khó hiểu, đoán từ source trước rồi dùng **`javap` kiểm chứng**, tránh suy diễn từ runtime class của argument.

## Tài liệu tham khảo chính thức (Java SE 17)

- [`java.lang.invoke.MethodHandle` — Signature polymorphism và Method handle invocation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html)
- [Java Language Specification `15.12.3` — Compile-Time Step 3: Is the Chosen Method Appropriate?](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12.3)
- [JVM Specification `2.9.3` — Signature Polymorphic Methods](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.9.3)
- [JVM Specification `5.4.3.3` — Method Resolution](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.3.3)
- [JVM Specification `6.5` — `invokevirtual`](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html#jvms-6.5.invokevirtual)
- [Java SE 17 `java.lang.invoke.MethodType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html)
