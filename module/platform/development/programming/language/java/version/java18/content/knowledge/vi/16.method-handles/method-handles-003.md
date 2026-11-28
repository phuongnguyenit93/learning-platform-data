# MethodHandle.type(): đọc chữ ký thực tế trước khi gọi hoặc tạo adapter

## Mục tiêu bài học

Trong chương **MethodHandle** của mô-đun Java 18, bài học này tập trung vào phương thức `java.lang.invoke.MethodHandle.type()` và cách sử dụng `MethodType` để xác định **chữ ký thực tế của một method handle** trước khi gọi hoặc tạo adapter. Đây là hợp đồng API còn áp dụng trên các JDK hiện đại.

Sau bài học, bạn có thể:

- Đọc kiểu trả về, số lượng và thứ tự kiểu tham số từ `handle.type()`.
- Phân biệt chữ ký phương thức Java được khai báo với chữ ký **của handle** sau khi lookup, bind receiver hoặc chuyển đổi.
- Dự đoán kiểu của handle cho instance method, static method, constructor và getter/setter.
- Giải thích vì sao `invokeExact` yêu cầu khớp cả kiểu tham số **lẫn kiểu trả về tại điểm gọi**.
- Dùng `type()` để kiểm tra điều kiện trước khi gọi `invoke`, `invokeExact`, `bindTo` hoặc tạo adapter bằng `asType`.
- Phân biệt kiểm tra chữ ký với kiểm tra quyền truy cập, chuyển đổi runtime và logic của phương thức đích.

> **Bối cảnh phiên bản:** Method Handle API xuất hiện trước Java 18 và vẫn được hỗ trợ trên JDK mới. JEP 416 của Java 18 dùng method handles để triển khai core reflection bên trong JDK; điều này không làm thay đổi hợp đồng công khai của `MethodHandle.type()`. Nội dung dưới đây chỉ dùng API tiêu chuẩn trong `java.lang.invoke`.

## 1. `MethodHandle.type()` trả về điều gì?

Một `MethodHandle` là tham chiếu có kiểu tới một thao tác có thể gọi: gọi method, tạo đối tượng, đọc/ghi field hoặc một thao tác đã được điều chỉnh bằng adapter. Mỗi handle luôn gắn với một **`MethodType`**.

Chữ ký:

~~~java
public MethodType type()
~~~

`type()` trả về `MethodType` mô tả **kiểu tham số và kiểu kết quả hiện tại của handle**. Thao tác này đọc thông tin kiểu; nó **không gọi phương thức đích** và không xử lý dữ liệu nghiệp vụ.

Các API quan trọng của `MethodType`:

| API | Ý nghĩa | Ví dụ với kiểu `(String,int)long` |
| --- | --- | --- |
| `type.parameterCount()` | Số tham số của handle | `2` |
| `type.parameterType(0)` | Kiểu tham số tại chỉ số 0 (đếm từ 0) | `String.class` |
| `type.parameterType(1)` | Kiểu tham số tại chỉ số 1 | `int.class` |
| `type.parameterArray()` | Mảng kiểu tham số | `[String.class, int.class]` |
| `type.parameterList()` | Danh sách kiểu tham số, theo thứ tự | `[String.class, int.class]` |
| `type.returnType()` | Kiểu kết quả của handle | `long.class` |
| `type.toMethodDescriptorString()` | Descriptor kiểu JVM | `(Ljava/lang/String;I)J` |
| `type.equals(expectedType)` | So sánh chữ ký đầy đủ | `true` nếu cùng thứ tự tham số và kiểu trả về |

`MethodType` là đối tượng bất biến. Những phép biến đổi như `changeParameterType(...)`, `insertParameterTypes(...)` hay `changeReturnType(...)` tạo ra một `MethodType` mô tả chữ ký mới, thay vì sửa đối tượng cũ.

Để khai báo một chữ ký mong đợi:

~~~java
import java.lang.invoke.MethodType;

MethodType expected =
        MethodType.methodType(long.class, String.class, int.class);

System.out.println(expected);                     // (String,int)long
System.out.println(expected.parameterCount());    // 2
System.out.println(expected.parameterType(0));    // class java.lang.String
System.out.println(expected.returnType());        // long
~~~

Trong `MethodType.methodType(...)`, **đối số đầu tiên là kiểu trả về**, sau đó mới đến các kiểu tham số. Vì thế `methodType(long.class, String.class, int.class)` diễn đạt `(String,int)long`, không phải `(long,String)int`.

### Một số quy tắc kiểu quan trọng

- Tham số có thể là kiểu primitive, reference hoặc array; **`void` chỉ được dùng làm kiểu trả về**, không phải kiểu tham số.
- `String.class` và `Object.class` là hai kiểu khác nhau, dù `String` là lớp con của `Object`.
- `int.class` khác `Integer.class`: chữ ký handle không tự xóa khác biệt primitive và wrapper.
- Thứ tự tham số là một phần của chữ ký: `(String,int)long` khác `(int,String)long`.
- `(String)int` khác `(String)Integer` vì kiểu trả về khác nhau.
- Dùng `MethodType.equals(...)` để so sánh nội dung chữ ký. Không dựa vào toán tử `==` để diễn đạt yêu cầu kiểu.

## 2. Chữ ký của handle có thể khác chữ ký phương thức Java

Điểm dễ nhầm nhất là **receiver**.

Trong mã Java, một phương thức instance có thể được khai báo như sau:

~~~java
class Counter {
    int add(int delta) {
        return delta + 10;
    }
}
~~~

Chữ ký phương thức khai báo là `int add(int)`. Nhưng khi lấy handle qua `Lookup.findVirtual(Counter.class, "add", MethodType.methodType(int.class, int.class))`, kiểu của handle là:

~~~text
(Counter,int)int
~~~

Lý do: handle của instance method cần biết **đối tượng receiver** tại điểm gọi. Receiver trở thành **tham số đầu tiên của handle**.

Đối với một static method:

~~~java
static int doubleValue(int x) {
    return x * 2;
}
~~~

Handle thu được từ `findStatic` có kiểu:

~~~text
(int)int
~~~

Nó không có receiver instance.

| Cách lấy handle | Ví dụ thành viên | `handle.type()` thường có dạng |
| --- | --- | --- |
| `findVirtual` | `Counter.add(int) : int` | `(Counter,int)int` |
| `findStatic` | `Counter.label(int) : String` | `(int)String` |
| `findConstructor` | `new Counter(int)` | `(int)Counter` |
| `findGetter` | instance field `Counter.value : int` | `(Counter)int` |
| `findSetter` | instance field `Counter.value : int` | `(Counter,int)void` |
| `findStaticGetter` | static field `Metrics.total : long` | `()long` |
| `findStaticSetter` | static field `Metrics.total : long` | `(long)void` |

**Constructor là trường hợp đặc biệt:** khi gọi `Lookup.findConstructor`, bạn truyền `MethodType.methodType(void.class, ...)` để mô tả constructor khi lookup, nhưng **handle trả về** có kiểu kết quả là lớp được khởi tạo. Ví dụ `(int)Counter`, vì gọi handle tạo ra một `Counter`.

Các kiểu trong bảng là những trường hợp tra cứu trực tiếp không thêm adapter. Sau `bindTo`, `asType`, `asSpreader` hay tổ hợp khác, **phải đọc lại `type()` của handle mới**.

## 3. Ví dụ hoàn chỉnh: đọc kiểu trước khi gọi

Tạo file `HandleTypeDemo.java` bằng mã Java tiêu chuẩn sau:

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class HandleTypeDemo {
    public static class Counter {
        public int value;

        public Counter(int initial) {
            value = initial;
        }

        public int add(int delta) {
            value += delta;
            return value;
        }

        public static String label(int number) {
            return "n=" + number;
        }
    }

    private static void describe(String name, MethodHandle handle) {
        MethodType type = handle.type();

        System.out.println(name + " = " + type);
        System.out.println("  params = " + type.parameterCount());
        System.out.println("  returns = " + type.returnType().getTypeName());
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        // Chu ky khai bao de tim constructor: (int)void.
        MethodHandle constructor = lookup.findConstructor(
                Counter.class,
                MethodType.methodType(void.class, int.class));

        // Chu ky tra cuu method: (int)int.
        // Kieu handle nhan duoc: (Counter,int)int.
        MethodHandle instance = lookup.findVirtual(
                Counter.class,
                "add",
                MethodType.methodType(int.class, int.class));

        MethodHandle staticMethod = lookup.findStatic(
                Counter.class,
                "label",
                MethodType.methodType(String.class, int.class));

        MethodHandle getter =
                lookup.findGetter(Counter.class, "value", int.class);

        MethodHandle setter =
                lookup.findSetter(Counter.class, "value", int.class);

        describe("constructor", constructor);
        describe("instance", instance);
        describe("static", staticMethod);
        describe("getter", getter);
        describe("setter", setter);

        Counter counter = (Counter) constructor.invokeExact(10);

        int first = (int) instance.invokeExact(counter, 5);
        System.out.println("first = " + first); // 15

        // bindTo gan co dinh receiver, sau do handle khong can Counter.
        MethodHandle bound = instance.bindTo(counter);
        describe("bound", bound); // (int)int

        int second = (int) bound.invokeExact(2);
        System.out.println("second = " + second); // 17

        setter.invokeExact(counter, 20);
        int current = (int) getter.invokeExact(counter);
        System.out.println("current = " + current); // 20

        String name = (String) staticMethod.invokeExact(7);
        System.out.println("label = " + name); // n=7
    }
}
~~~

Biên dịch và chạy với JDK hiện đại:

~~~sh
javac HandleTypeDemo.java
java HandleTypeDemo
~~~

Các dòng mô tả chữ ký đáng chú ý:

~~~text
constructor = (int)Counter
instance = (Counter,int)int
static = (int)String
getter = (Counter)int
setter = (Counter,int)void
first = 15
bound = (int)int
second = 17
current = 20
label = n=7
~~~

Chương trình còn in `params` và `returns` sau mỗi chữ ký; bảng trên chỉ giữ các dòng quan trọng để tập trung vào cách đọc `type()`.

### Đọc từng kết quả

- `constructor.type()` là `(int)Counter`: handle nhận giá trị khởi tạo và trả về instance.
- `instance.type()` là `(Counter,int)int`: receiver có kiểu `Counter` xuất hiện trước `delta`.
- `staticMethod.type()` là `(int)String`: không có receiver.
- `getter.type()` là `(Counter)int`; `setter.type()` là `(Counter,int)void`.
- Sau `instance.bindTo(counter)`, kiểu mới là `(int)int` vì receiver đã được gắn cố định vào handle.

**Ghi nhớ:** kiểu của handle là kiểu tại thời điểm **sử dụng handle đang cầm**. Đừng suy ngược từ chữ ký method gốc nếu handle đã qua adapter.

## 4. `invokeExact`: phải khớp cả tham số lẫn kết quả tại điểm gọi

`MethodHandle.invokeExact(...)` là một phương thức có chữ ký đa hình (*signature-polymorphic*). Trình biên dịch Java tạo chữ ký điểm gọi dựa trên **kiểu tĩnh của các biểu thức đối số và ngữ cảnh kiểu kết quả**.

Xét handle với:

~~~text
(Counter,int)int
~~~

Các lời gọi:

~~~java
Counter c = new Counter(10);

// DUNG: kieu doi so (Counter,int), kieu ket qua int.
int result = (int) instance.invokeExact(c, 5);

// SAI VE KIEU KET QUA: diem goi doi Object, handle tra int.
// Object wrong = instance.invokeExact(c, 5);

// SAI VE KIEU THAM SO: Integer la reference type, khac int.
// int wrongArg = (int) instance.invokeExact(c, Integer.valueOf(5));
~~~

Hai dòng được chú thích “SAI” **có thể biên dịch nhưng gây `WrongMethodTypeException` khi thực thi** với handle `(Counter,int)int`. `invokeExact` không tự boxing/unboxing hoặc điều chỉnh chữ ký để sửa sự khác nhau giữa `Object` và `int` tại điểm gọi.

Trong ví dụ, biến `instance` thuộc mã `HandleTypeDemo` ở mục trước. `WrongMethodTypeException` phản ánh lỗi khớp kiểu giữa điểm gọi và `handle.type()`, không phải lỗi do phần thân `Counter.add` tự ném.

### Cách kiểm tra trước khi gọi

~~~java
MethodType actual = instance.type();
MethodType expected = MethodType.methodType(
        int.class, Counter.class, int.class);

if (!actual.equals(expected)) {
    throw new IllegalStateException(
            "Sai chu ky: expected=" + expected + ", actual=" + actual);
}

int result = (int) instance.invokeExact(new Counter(10), 5);
~~~

Kiểm tra này hữu ích khi code lấy handle từ registry, factory hoặc plugin ở runtime. Nó phát hiện **sai chữ ký dự kiến** trước khi thực hiện lời gọi thật. Tuy nhiên, phép kiểm tra `type()` không thay thế được việc xử lý ngoại lệ từ phương thức đích.

### Phương thức trả về `void`

Nếu handle có kiểu `(Counter,int)void` (chẳng hạn setter), hãy gọi `invokeExact` trong **ngữ cảnh statement không yêu cầu kết quả**:

~~~java
setter.invokeExact(counter, 30);
~~~

Viết `Object result = setter.invokeExact(counter, 30);` sẽ tạo một kiểu trả về tại điểm gọi khác `void`; đó không phải một lời gọi exact hợp lệ cho handle kiểu `(Counter,int)void`.

## 5. `invoke` có khả năng thích nghi, nhưng không vô hạn

`MethodHandle.invoke(...)` cũng là lời gọi signature-polymorphic, nhưng nó có thể sử dụng quy tắc tương thích kiểu giống cơ chế `asType(...)` để điều chỉnh giữa chữ ký điểm gọi và kiểu thật của handle.

Ví dụ, handle kiểu `(Counter,int)int` có thể được gọi bằng:

~~~java
Counter counter = new Counter(10);

// Tai diem goi yeu cau Object; invoke cho phep box int thanh Integer.
Object boxed = instance.invoke(counter, 5);
System.out.println(boxed); // 15
~~~

Với `invokeExact`, cùng kiểu kết quả `Object` sẽ không khớp `int`. Điểm khác biệt nằm ở **cơ chế thích nghi của `invoke`**, không phải ở việc `handle.type()` đã đổi.

Tuy nhiên, `invoke` vẫn có thể gây `WrongMethodTypeException` nếu chữ ký điểm gọi không thể thích nghi theo quy tắc cho phép. Khi chuyển đổi giá trị reference thực tế, cũng có thể gặp `ClassCastException` hoặc lỗi unboxing null. Không được coi `invoke` là phép ép kiểu tùy ý.

| API | Cách dùng | Điểm cần chú ý |
| --- | --- | --- |
| `invokeExact(...)` | Khi biết chính xác `handle.type()` và kiểu tại điểm gọi | Không có tự động chuyển đổi tại điểm gọi |
| `invoke(...)` | Khi cần dùng những chuyển đổi được Method Handle hỗ trợ | Chuyển đổi phải hợp lệ; không bảo đảm mọi lời gọi đều thành công |
| `invokeWithArguments(...)` | Khi số lượng/đối số được cung cấp động, thường qua mảng hoặc danh sách | Linh hoạt hơn nhưng có overhead; không mặc nhiên tương đương `invokeExact` |

**Quan trọng:** sau một lời gọi `invoke(...)`, `handle.type()` của handle gốc **vẫn như cũ**. Tính thích nghi tại lời gọi không đồng nghĩa đã thay đổi đối tượng handle.

## 6. Dùng `type()` trước khi tạo adapter với `asType`

`MethodHandle.asType(MethodType newType)` tạo ra **handle mới** có kiểu `newType`, với lớp chuyển đổi phù hợp để kết nối lời gọi mới với handle gốc. Đây là kỹ thuật thường dùng khi một framework muốn chuẩn hóa nhiều handle về cùng một chữ ký.

Giả sử handle gốc của `Counter.label(int)`:

~~~text
(int)String
~~~

Ta muốn caller dùng giao diện tổng quát:

~~~text
(Object)Object
~~~

Mã minh họa (tiếp tục trong ngữ cảnh `HandleTypeDemo`):

~~~java
MethodType wanted =
        MethodType.methodType(Object.class, Object.class);

MethodHandle generic = staticMethod.asType(wanted);

System.out.println(staticMethod.type()); // (int)String
System.out.println(generic.type());      // (Object)Object

Object result = (Object) generic.invokeExact(
        (Object) Integer.valueOf(8));

System.out.println(result);              // n=8
~~~

Ở adapter này:

1. Giá trị ở điểm gọi có kiểu tĩnh `Object`, nhưng giá trị runtime phải có thể chuyển sang `int` theo quy tắc cho phép (trong ví dụ là `Integer`).
2. Kết quả từ method đích là `String`, được nhìn dưới kiểu `Object` của adapter.
3. Handle gốc vẫn có `type() == (int)String`; chỉ handle `generic` có kiểu `(Object)Object`.

Nếu caller truyền `"not-an-int"` cho adapter, chữ ký điểm gọi vẫn khớp `(Object)Object`, nhưng chuyển đổi **giá trị** sang `int` có thể thất bại khi chạy. `type()` giúp kiểm tra **hợp đồng kiểu tĩnh của handle**, không chứng minh mọi giá trị đầu vào đều hợp lệ.

### Kiểm tra tính thích nghi trước và sau

~~~java
MethodHandle adaptOrFail(MethodHandle original, MethodType required) {
    MethodType actual = original.type();

    if (actual.equals(required)) {
        return original;
    }

    try {
        MethodHandle adapted = original.asType(required);

        if (!adapted.type().equals(required)) {
            throw new IllegalStateException("Adapter sai chu ky");
        }

        return adapted;
    } catch (java.lang.invoke.WrongMethodTypeException ex) {
        throw new IllegalArgumentException(
                "Khong the doi " + actual + " sang " + required, ex);
    }
}
~~~

Đây là mẫu cho một phương thức hỗ trợ nằm trong lớp Java có import `MethodHandle` và `MethodType` như phần ví dụ trước. Không phải mọi cặp kiểu đều chuyển đổi được. Nếu không thể tạo adapter hợp lệ, `asType` báo `WrongMethodTypeException`; khi tạo adapter thành công, lời gọi **vẫn có thể** thất bại vì giá trị runtime không chuyển đổi được hoặc method đích ném ngoại lệ.

**Tránh suy diễn:** `asType` không cho phép tùy ý chuyển hẹp primitive. Những chuyển đổi mạnh hơn hoặc khác biệt rõ ràng cần API phù hợp, và phải được đánh giá riêng về ngữ nghĩa.

## 7. `bindTo` thay đổi chữ ký mà `type()` trả về

`bindTo(Object x)` gắn trước giá trị `x` cho **tham số đầu tiên kiểu reference** của handle; handle mới giảm đi một tham số. Với instance method, tham số này thường chính là receiver.

Từ handle:

~~~text
instance.type() = (Counter,int)int
~~~

Sau khi bind:

~~~java
Counter receiver = new Counter(10);
MethodHandle bound = instance.bindTo(receiver);

System.out.println(instance.type()); // (Counter,int)int
System.out.println(bound.type());    // (int)int

int result = (int) bound.invokeExact(5); // 15
~~~

Nếu vẫn truyền `receiver` vào `bound.invokeExact(receiver, 5)`, điểm gọi có hai tham số trong khi `bound.type()` chỉ nhận một. Đây là lỗi ghép nối phổ biến khi code lấy handle từ nơi khác.

`bindTo` yêu cầu tham số đầu tiên của handle có kiểu reference và giá trị phù hợp. Không thể dùng nó để gắn trực tiếp một tham số đầu tiên `int` của handle kiểu `(int)int`. Nếu cần chèn/gắn tham số ở vị trí khác, hãy tìm hiểu adapter `MethodHandles.insertArguments(...)` và luôn xem lại `type()` sau khi tạo handle mới.

### `type()` phản ánh adapter hiện tại

Các adapter sau có thể làm thay đổi danh sách tham số:

| Adapter | Ý tưởng | Điều cần đọc lại |
| --- | --- | --- |
| `bindTo(receiver)` | Gắn đối số reference đầu tiên | Kiểu handle không còn tham số đầu tiên |
| `MethodHandles.insertArguments(...)` | Gắn trước một hoặc nhiều đối số tại vị trí chỉ định | Số lượng và vị trí tham số còn lại |
| `MethodHandles.dropArguments(...)` | Thêm tham số bị bỏ qua khi gọi target | Kiểu handle có thêm các tham số |
| `asType(newType)` | Tạo đường gọi có chữ ký mới với chuyển đổi hợp lệ | Kiểu mới đúng bằng `newType` |
| `asSpreader(...)` | Gom một nhóm đối số thành tham số mảng tại điểm gọi | Vị trí và kiểu của mảng |
| `asCollector(...)` | Trải một tham số mảng thành nhiều tham số tại điểm gọi | Số lượng kiểu tham số của handle mới |

Phải xem `type()` trên **kết quả adapter**, không dùng thông tin của handle ban đầu để suy đoán.

## 8. Ví dụ kiểm chứng `asSpreader` và `asCollector`

Hai adapter này hữu ích khi code của framework nhận tham số dưới dạng mảng, còn method đích cần tham số riêng hoặc ngược lại.

Ví dụ với phương thức static:

~~~java
public static String join(String left, String right) {
    return left + "/" + right;
}
~~~

Handle trực tiếp có kiểu:

~~~text
(String,String)String
~~~

Chuyển thành handle nhận một mảng:

~~~java
MethodHandle join = lookup.findStatic(
        Example.class,
        "join",
        MethodType.methodType(String.class, String.class, String.class));

MethodHandle spreader = join.asSpreader(String[].class, 2);

System.out.println(join.type());     // (String,String)String
System.out.println(spreader.type()); // (String[])String

String text = (String) spreader.invokeExact(
        new String[] {"a", "b"});
~~~

Trong đoạn minh họa, `Example` là lớp khai báo phương thức `join`; `lookup` là một `MethodHandles.Lookup` có quyền truy cập phù hợp. Kết quả `text` là `"a/b"`.

Ở chiều ngược lại, nếu handle gốc nhận `String[]` thì `asCollector(String[].class, 2)` có thể tạo handle với hai đối số `String` riêng lẻ. `type()` là cách kiểm chứng ngay số lượng và vị trí tham số sau khi tạo.

**Phân biệt với varargs:** một handle được đánh dấu varargs collector có thể có cách nhận đối số linh hoạt khi gọi qua một số đường `invoke`, trong khi `type()` vẫn mô tả chữ ký cụ thể (thường có tham số mảng ở cuối). Nếu cần biết trạng thái này, dùng `handle.isVarargsCollector()`; không chỉ nhìn `toString()` hay đếm tham số.

## 9. Dùng `type()` khi xây registry hoặc gọi plugin

Ứng dụng có thể nhận một handle từ factory/plugin mà không biết chắc chữ ký cho đến runtime. Khi đó, một quy trình an toàn có thể là:

1. Định nghĩa chữ ký mà hệ thống hỗ trợ bằng `MethodType.methodType(...)`.
2. Nhận handle rồi đọc `actual = handle.type()`.
3. Nếu `actual.equals(expected)`, dùng handle theo đúng chữ ký đó.
4. Nếu khác nhau nhưng được phép chuyển đổi, tạo adapter bằng `asType(expected)` và kiểm tra kiểu mới.
5. Nếu không thể thích nghi hoặc thay đổi làm sai hợp đồng dữ liệu, từ chối cấu hình và thông báo chữ ký thực tế.
6. Khi gọi handle, vẫn xử lý lỗi do chuyển đổi dữ liệu và lỗi từ method đích.

Ví dụ kiểm tra một handler chuẩn hóa về `(String)String`:

~~~java
static MethodHandle requireStringHandler(MethodHandle candidate) {
    MethodType expected =
            MethodType.methodType(String.class, String.class);

    MethodType actual = candidate.type();
    if (!actual.equals(expected)) {
        throw new IllegalArgumentException(
                "Handler phai co kieu " + expected +
                ", nhan duoc " + actual);
    }

    return candidate;
}
~~~

Nếu hệ thống cho phép cả các handle `(Object)Object`, hãy **định nghĩa rõ** chuyển đổi nào được cho phép trước khi tạo adapter. Tự động gọi `asType` cho tất cả handle chỉ vì nó có thể tạo ra adapter là quyết định có rủi ro: giá trị runtime có thể không tương thích, hoặc chính sách hợp đồng của plugin không cho phép ép kiểu như vậy.

### Phân biệt kiểm tra kiểu và kiểm tra quyền

`MethodHandle.type()` **không cho biết**:

- Handle này được tạo từ method private hay public, hoặc từ một adapter phức tạp.
- Module nào có quyền lookup vào member đích.
- Method đích sẽ ném ngoại lệ nào ở runtime.
- Việc gọi handle có tạo side effect hay có an toàn khi gọi đồng thời.
- Handle hiện tại sẽ nhanh hơn lời gọi reflection trong workload cụ thể hay không.

Quyền truy cập được kiểm tra theo hợp đồng của `MethodHandles.Lookup` và các cơ chế liên quan khi **tạo/tìm handle**; `type()` chỉ mô tả kiểu thao tác của handle đã nhận. Không dùng `type()` như một cách vượt kiểm tra quyền hoặc suy đoán nội bộ JDK.

## 10. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `WrongMethodTypeException` khi dùng `invokeExact` | Kiểu tham số hoặc kiểu kết quả tại điểm gọi khác `handle.type()` | In/kiểm tra `type()`, sửa cast và kiểu biểu thức tại điểm gọi |
| `WrongMethodTypeException` khi gọi `asType` | Hai method type không thể thích nghi theo quy tắc hỗ trợ | Rà soát chuyển đổi và thiết kế adapter khác hoặc từ chối |
| `ClassCastException` ở adapter dù `type()` đúng | Giá trị runtime bên dưới kiểu reference không phù hợp | Kiểm tra giá trị đầu vào và các bước chuyển đổi trước khi gọi |
| Gọi bound handle nhưng vẫn truyền receiver | Receiver đã bị gắn bằng `bindTo`, chữ ký giảm một tham số | Kiểm tra `bound.type()` |
| Constructor handle bị nghĩ là trả `void` | Nhầm method type dùng để tra cứu với kiểu handle trả về | Đọc `constructor.type()`; kết quả là lớp được khởi tạo |
| Nhầm `Integer.class` với `int.class` | Primitive và wrapper là hai loại khác nhau | So sánh chính xác các kiểu và chủ động quyết định boxing/unboxing |
| Nhầm vị trí tham số mảng sau `asSpreader` | Adapter đổi hình dạng tham số | Đọc `type()` của adapter mới |
| Nhầm handle instance với static | Instance handle có tham số receiver; static không có | Dựa trên `type()` và cách lookup, không suy từ tên method |
| Đọc `type()` rồi cho rằng logic chắc chắn thành công | Kiểu hợp lệ không bảo đảm quyền, trạng thái và dữ liệu hợp lệ | Xử lý lỗi thao tác đích riêng |

### Checklist trước khi gọi handle nhận từ nguồn động

~~~text
[ ] Da doc handle.type() va ghi nhan day du returnType + parameterTypes?
[ ] Da phan biet instance receiver voi tham so thuc su?
[ ] Da kiem tra type() tren handle SAU bindTo/asType/adapter?
[ ] Neu invokeExact, kieu tinh tai diem goi da khop hoan toan?
[ ] Neu invoke/asType, da chap nhan ro quy tac chuyen doi?
[ ] Da xu ly loi runtime va loi do phuong thuc dich?
[ ] Da kiem tra quyen lookup khi tao handle o dung module?
~~~

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Một instance method có khai báo `String name(int id)` trên lớp `Account`. Nếu lấy qua `findVirtual`, handle trực tiếp có kiểu nào?

**Trả lời:** `(Account,int)String`. Receiver `Account` là tham số đầu tiên của handle, dù không được viết trong danh sách tham số khai báo của method Java.

**Câu 2.** `Lookup.findConstructor(Account.class, methodType(void.class, String.class))` trả handle có kiểu `(String)void` hay `(String)Account`?

**Trả lời:** `(String)Account`. `void` mô tả constructor khi lookup, nhưng handle dùng để tạo và trả về một `Account`.

**Câu 3.** `handle.type()` là `(int)int`. Vì sao `Object result = handle.invokeExact(5)` sai kiểu?

**Trả lời:** Điểm gọi yêu cầu kết quả `Object`, trong khi handle trả `int`. `invokeExact` bắt buộc kiểu kết quả trùng khớp. Đổi thành `int result = (int) handle.invokeExact(5)` nếu tham số và ngữ cảnh phù hợp, hoặc dùng cơ chế thích nghi có chủ đích.

**Câu 4.** Handle có kiểu `(Account,int)int` được `bindTo(account)`. Khi gọi handle mới còn cần truyền `account` không?

**Trả lời:** Không. `bindTo` gắn đối số reference đầu tiên, nên kiểu handle mới là `(int)int`; chỉ còn tham số `int`.

**Câu 5.** Một adapter `asType(methodType(Object.class, Object.class))` được tạo thành công từ handle `(int)String`. Có thể truyền mọi `Object` và chắc chắn gọi thành công không?

**Trả lời:** Không. Chữ ký adapter là `(Object)Object`, nhưng giá trị đối số runtime vẫn phải chuyển được sang `int`. Ví dụ `Integer` tương thích; một đối tượng `String` bất kỳ không được tự chuyển thành `int`.

**Câu 6.** Vì sao phải đọc lại `type()` sau `asSpreader` hoặc `asCollector`?

**Trả lời:** Vì adapter có thể thay đổi số lượng và cấu trúc tham số của handle. Điểm gọi phải khớp với chữ ký **sau chuyển đổi**, không phải chữ ký gốc.

## Ghi nhớ

- **`MethodHandle.type()` là nguồn thông tin trực tiếp về chữ ký hiện tại của handle**: thứ tự tham số, kiểu tham số và kiểu kết quả.
- Instance handle thường mang receiver như **tham số đầu tiên**; static handle không có receiver; constructor handle trả về **kiểu đối tượng được tạo**.
- `invokeExact` yêu cầu chữ ký tại điểm gọi khớp chính xác, **kể cả kiểu trả về**. `invoke` cho phép một số thích nghi, nhưng vẫn có thể lỗi nếu chuyển đổi không hợp lệ.
- `bindTo`, `asType`, `asSpreader` và các adapter khác có thể đổi `type()` của **handle mới**; luôn kiểm tra sau khi tạo.
- `type()` xác nhận **hình dạng kiểu của thao tác**, không xác nhận quyền truy cập, tính đúng đắn của giá trị runtime hoặc thành công của logic đích.
- Trên JDK hiện đại, hãy kiểm tra chữ ký thật, tạo adapter theo hợp đồng rõ ràng và xử lý ngoại lệ ở đúng tầng.

**Tài liệu đối chiếu:** Javadoc `java.lang.invoke.MethodHandle` (đặc biệt `type`, `invokeExact`, `invoke`, `asType`, `bindTo`); `java.lang.invoke.MethodType`; `java.lang.invoke.MethodHandles.Lookup`. JEP 416 — *Reimplement Core Reflection with Method Handles* (`https://openjdk.org/jeps/416`) giải thích vai trò của method handles trong triển khai core reflection từ Java 18.
