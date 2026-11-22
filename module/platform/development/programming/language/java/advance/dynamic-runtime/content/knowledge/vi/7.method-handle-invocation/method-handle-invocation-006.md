# 7.6. invokeWithArguments và cái giá của đường gọi dùng Object

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích chính xác `MethodHandle.invokeWithArguments` nhận một mảng `Object...` hoặc `List<?>` và trả về `Object` như thế nào.
- Phân biệt đường gọi tổng quát `invokeWithArguments` với `invokeExact`, `invoke` và các adapter `asType`, `asSpreader`.
- Chỉ ra chi phí tiềm tàng của boxing/unboxing, mảng đối số, chuyển đổi kiểu, và mất thông tin kiểu tĩnh khi lặp qua một đường gọi dùng `Object`.
- Nhận diện các lỗi điển hình về số đối số, kiểu dữ liệu, `null`, receiver và Java varargs.
- Quyết định khi nào tính linh hoạt đáng giá và khi nào cần cấu trúc lời gọi có kiểu rõ ràng; kiểm tra bằng ví dụ Java 17+ chạy được.

## 1. Bài toán: đã có MethodHandle, nhưng đối số chỉ có dạng Object

`MethodHandle` là tham chiếu có kiểu tới một thao tác có thể thực thi: method, constructor, field hoặc một chuỗi adapter. Mỗi handle mang một `MethodType` gồm **danh sách kiểu tham số và kiểu trả về**. Ví dụ một method `static int sum(int, int)` có handle kiểu:

~~~text
(int,int)int
~~~

Đó là kiểu của **handle đích**, không phụ thuộc việc chương trình lấy dữ liệu đầu vào từ đâu.

Trong lời gọi Java thông thường, trình biên dịch nhìn thấy số lượng và kiểu tĩnh của đối số:

~~~java
// Fragment minh họa, giả định sum là MethodHandle có kiểu (int,int)int.
int result = (int) sum.invokeExact(20, 22);
~~~

Nhưng ứng dụng đọc lệnh từ JSON, cấu hình, một công cụ plugin hoặc hàng dữ liệu lại thường chỉ có một danh sách:

~~~java
// Fragment minh họa, không phải chương trình độc lập.
Object[] arguments = { Integer.valueOf(20), Integer.valueOf(22) };
Object result = sum.invokeWithArguments(arguments);
~~~

`invokeWithArguments` là cầu nối thuận tiện giữa **dữ liệu runtime đã được đóng vào Object** với **handle có MethodType cụ thể**. Nó không tự tìm method theo tên, không tự chọn overload, cũng không biến các giá trị `Object` thành một call site `invokeExact` có kiểu nguyên thủy.

Câu hỏi trọng tâm của bài: **khi đã biết handle và kiểu ổn định, việc đi qua một danh sách Object có chi phí và giới hạn gì?**

## 2. Hợp đồng API của invokeWithArguments

Java SE 17 định nghĩa hai overload chính của `MethodHandle`:

~~~java
// Khai báo API để tham khảo; không phải class người học cần triển khai.
public Object invokeWithArguments(Object... arguments) throws Throwable;
public Object invokeWithArguments(java.util.List<?> arguments) throws Throwable;
~~~

Chúng là **method Java thông thường**. Đây là điểm khác với hai tên đặc biệt `invokeExact` và `invoke`: hai method đó là **signature-polymorphic**, nên JVM xem kiểu đối số và kiểu trả về do call site Java biên dịch ghi vào bytecode.

Với `invokeWithArguments`:

1. **Số đối số** lấy từ độ dài mảng `Object[]` hoặc `List<?>.` Mỗi phần tử biểu diễn **một đối số**; không phải suy ra kiểu bằng tên biến.
2. **Kiểu tĩnh ở ranh giới gọi tổng quát** được xem như `Object`. JVM phải thích ứng với tham số được chỉ định trong `handle.type()`.
3. Đường chuyển đổi tương ứng có thể thực hiện **reference cast**, **unboxing**, **primitive widening** và **thu gom varargs** nếu handle là varargs collector.
4. **Giá trị trả về** được biểu diễn bằng `Object`: kết quả primitive được boxing (ví dụ `int` thành `Integer`); handle trả `void` cho kết quả `null`.
5. Nếu kiểu/số đối số không phù hợp thì lời gọi có thể ném lỗi. Ngoại lệ do **method đích** ném có thể đi thẳng ra dưới dạng `Throwable`; không tự động được gói thành `InvocationTargetException` như `Method.invoke`.

Overload `invokeWithArguments(List<?>)` có ý nghĩa tương đương việc lấy các phần tử của list thành mảng rồi gọi overload mảng (theo hợp đồng API). Điều này rất tiện cho đầu vào đã ở dạng `List`, nhưng cũng có thể kéo theo bước tạo mảng trung gian.

**Lưu ý quan trọng:** Khai báo `Object...` ở đây thuộc **API của invokeWithArguments**, không tự biến handle đích thành method nhận `Object[]`. Từng phần tử mảng được trải ra thành từng đối số đối với handle.

### 2.1. Ba đường gọi nhìn giống nhau nhưng hợp đồng khác nhau

| Cách gọi | Thông tin kiểu ở call site | Chuyển đổi cho phép | Kiểu kết quả ở call site | Phù hợp khi |
| --- | --- | --- | --- | --- |
| `invokeExact(...)` | Descriptor phải **trùng tuyệt đối** `MethodType` của handle | Không có adaptation kiểu ở điểm gọi | Phải trùng kiểu trả về của handle | Đã biết chữ ký chính xác, đường gọi ổn định |
| `invoke(...)` | Descriptor được xác định tĩnh từ biểu thức Java | Có thể thích nghi bằng quy tắc `asType` | Theo descriptor tại call site | Chữ ký ở call site được biết nhưng cần conversion hợp lệ |
| `invokeWithArguments(Object...)` | Các đối số nhìn như `Object`, số lượng từ mảng | Chuyển đổi chung như gọi `invoke` qua Object | Luôn là `Object` | Danh sách đối số thực sự chỉ được quyết định ở runtime |
| `invokeWithArguments(List<?>)` | Các phần tử `List` nhìn như `Object` | Cùng ý nghĩa với dạng mảng | Luôn là `Object` | Cầu nối từ cấu trúc dữ liệu đã có dạng list |

Đừng rút ra kết luận rằng `invoke` luôn chậm hoặc `invokeExact` luôn nhanh trong mọi trường hợp: tối ưu phụ thuộc JIT, kiểu handle, độ ổn định call site, cấu trúc adapter và workload. Bảng mô tả **hợp đồng ngữ nghĩa**, chưa phải kết quả benchmark.

## 3. Từ MethodType cụ thể sang lời gọi Object

Giả sử có handle:

~~~text
MethodType đích:       (int, int)int
Dữ liệu thực tế:       Object[] { Integer(20), Integer(22) }
Tại ranh giới generic: (Object, Object)Object
                          |       |
                          v       v
                    unbox Integer thành int
                          |
                     gọi sum(int,int)
                          |
                  kết quả int = 42
                          |
                    box thành Integer
                          |
                 trả về Object tham chiếu
~~~

Sơ đồ cho thấy **chuyển đổi ở ranh giới**, không phải yêu cầu JVM luôn dựng mọi adapter hoặc cấp phát mọi object đúng như sơ đồ trong từng lần gọi. JIT có thể loại một số boxing/array nếu chứng minh không cần chúng. Tuy vậy ở cấp độ API, đường gọi generic vẫn buộc chương trình làm việc với `Object` thay vì truyền/nhận trực tiếp `int`.

Những điều chuyển đổi có thể và không thể làm:

- `Integer(20)` có thể được **unbox** cho tham số `int`.
- `Short(20)` có thể được unbox thành `short`, rồi **primitive widening** thành `int`.
- `"20"` là `String`; nó **không tự được parse** thành số `20`. Đây không phải cơ chế chuyển đổi dữ liệu JSON hay text.
- `null` không thể được unbox thành `int`, nên có thể ném `NullPointerException`.
- Số phần tử của đối số phải phù hợp arity của handle, trừ trường hợp handle có khả năng thu gom varargs.
- Nếu handle đại diện cho một **instance method chưa bind receiver**, receiver là **đối số đầu tiên** trong `MethodType` của handle; đường gọi dùng Object cũng phải truyền nó.

## 4. Ví dụ đầy đủ: invokeExact, invoke và invokeWithArguments

Lưu file **InvokeObjectBridgeDemo.java**.

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;
import java.util.List;

public class InvokeObjectBridgeDemo {
    static int sum(int left, int right) {
        return left + right;
    }

    static void record(String text) {
        System.out.println("record=" + text);
    }

    static final class Calculator {
        int triple(int n) {
            return n * 3;
        }
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodHandle sum = lookup.findStatic(
                InvokeObjectBridgeDemo.class,
                "sum",
                MethodType.methodType(int.class, int.class, int.class));

        System.out.println("type=" + sum.type());
        int exact = (int) sum.invokeExact(20, 22);
        int inexact = (int) sum.invoke(20, 22);
        Object dynamic = sum.invokeWithArguments(20, 22);
        System.out.println("exact=" + exact);
        System.out.println("invoke=" + inexact);
        System.out.println("objectResult=" + dynamic);
        System.out.println("resultClass=" + dynamic.getClass().getSimpleName());
        System.out.println("list=" + sum.invokeWithArguments(List.of(20, 22)));
        System.out.println("objectArray="
                + sum.invokeWithArguments(new Object[]{20, 22}));
        System.out.println("widen="
                + sum.invokeWithArguments(Short.valueOf((short) 20), 22));

        try {
            sum.invokeWithArguments(20);
        } catch (WrongMethodTypeException ex) {
            System.out.println("wrongArity=" + ex.getClass().getSimpleName());
        }
        try {
            sum.invokeWithArguments("20", 22);
        } catch (ClassCastException ex) {
            System.out.println("wrongType=" + ex.getClass().getSimpleName());
        }
        try {
            sum.invokeWithArguments((Object) null, 22);
        } catch (NullPointerException ex) {
            System.out.println("nullPrimitive=" + ex.getClass().getSimpleName());
        }

        MethodHandle record = lookup.findStatic(
                InvokeObjectBridgeDemo.class,
                "record",
                MethodType.methodType(void.class, String.class));
        Object noValue = record.invokeWithArguments("ok");
        System.out.println("voidReturnsNull=" + (noValue == null));

        MethodHandle triple = lookup.findVirtual(
                Calculator.class, "triple", MethodType.methodType(int.class, int.class));
        System.out.println("virtualType=" + triple.type());
        System.out.println("virtual=" + triple.invokeWithArguments(new Calculator(), 14));

        MethodHandle spread = sum.asSpreader(Object[].class, 2);
        System.out.println("spreadType=" + spread.type());
        int spreadValue = (int) spread.invokeExact(new Object[]{20, 22});
        System.out.println("spreadResult=" + spreadValue);

        MethodHandle objectAdapter = sum.asType(
                MethodType.methodType(Object.class, Object.class, Object.class));
        System.out.println("adapterType=" + objectAdapter.type());
        Object adapted = (Object) objectAdapter.invokeExact(
                (Object) Integer.valueOf(20), (Object) Integer.valueOf(22));
        System.out.println("adapterResult=" + adapted);
    }
}
~~~

Chạy bằng JDK 17+:

~~~bash
javac -encoding UTF-8 InvokeObjectBridgeDemo.java
java InvokeObjectBridgeDemo
~~~

Stdout:

~~~text
type=(int,int)int
exact=42
invoke=42
objectResult=42
resultClass=Integer
list=42
objectArray=42
widen=42
wrongArity=WrongMethodTypeException
wrongType=ClassCastException
nullPrimitive=NullPointerException
record=ok
voidReturnsNull=true
virtualType=(Calculator,int)int
virtual=42
spreadType=(Object[])int
spreadResult=42
adapterType=(Object,Object)Object
adapterResult=42
~~~

### 4.1. Vì sao exact và invoke đều ra 42?

Tại hai call site:

~~~java
// Fragment từ chương trình đã cho:
int exact = (int) sum.invokeExact(20, 22);
int inexact = (int) sum.invoke(20, 22);
~~~

Javac tạo descriptor **(int,int)int** cho cả hai lời gọi; nó trùng với `sum.type()`. Không có nhu cầu đổi kiểu dữ liệu. Với `invokeExact`, ngay cả **kiểu trả về tại call site** cũng phải trùng chính xác; vì thế phép cast kết quả sang `int` trong biểu thức có ý nghĩa xác định descriptor.

Nếu viết:

~~~java
// Fragment minh họa lỗi ở runtime; không có trong main ở trên:
Object wrongReturn = sum.invokeExact(20, 22);
~~~

Call site đòi descriptor trả `Object` trong khi handle thực trả `int`: chương trình có thể biên dịch, nhưng khi thực hiện lời gọi exact sẽ gặp `WrongMethodTypeException`. Không thể chỉ nhìn kiểu đối số và bỏ qua kiểu trả về của `invokeExact`.

### 4.2. Vì sao objectResult là Integer?

`sum.invokeWithArguments(20, 22)` nhận các đối số qua đường Java `Object...`: giá trị nguyên thủy được biểu diễn bằng wrapper `Integer` ở ranh giới Object. Lời gọi điều chỉnh cho tham số `int`, method tính ra `int 42`; kết quả trả qua API `Object` nên có dạng `Integer`. Bởi vậy:

~~~text
objectResult=42
resultClass=Integer
~~~

Chương trình muốn dùng tiếp kết quả như `int` phải kiểm tra/ép kiểu thích hợp, ví dụ `int number = (int) sum.invokeWithArguments(20, 22);`. Đường gọi như vậy có thêm ranh giới boxing/unboxing so với `invokeExact` có descriptor primitive. Đừng mặc định mỗi lần đều có allocation vật lý; đó là vấn đề tối ưu JIT cần đo.

### 4.3. Vì sao Short được chấp nhận còn String bị từ chối?

Đối số `Short` có thể được unbox rồi widen thành `int`, nên `widen=42`. Nhưng `"20"` không có phép chuyển đổi hợp lệ thành `int` theo quy tắc `asType`; ví dụ này ném `ClassCastException`.

Lời gọi chỉ truyền một đối số cho `sum(int,int)` có arity không phù hợp, nên xảy ra `WrongMethodTypeException`. Lời gọi truyền `null` ở vị trí `int` yêu cầu unboxing từ null nên ném `NullPointerException`.

Ba lỗi này minh họa **ba nguyên nhân khác nhau**: số đối số, kiểu dữ liệu, và giá trị null tại conversion primitive. Không nên gộp chúng thành “method không tồn tại”.

### 4.4. Vì sao void trả null, instance method thêm receiver?

Handle cho method `record(String)` trả `void`, nhưng API tổng quát trả `Object`; theo hợp đồng, giá trị quan sát được là `null` sau khi method in dòng `record=ok`.

Handle `findVirtual(Calculator.class, "triple", (int)int)` có kiểu runtime `(Calculator,int)int`. Đối số thứ nhất phải là **receiver Calculator**, tiếp theo mới là tham số `14`. Nếu bạn gọi `triple.invokeWithArguments(14)`, thiếu receiver và sai arity. Bạn có thể dùng `bindTo(calculator)` để tạo handle mới đã cố định receiver, nhưng cần xem lại `type()` sau bước bind.

### 4.5. Hai adapter trong ví dụ không đồng nghĩa “không còn Object cost”

`sum.asSpreader(Object[].class, 2)` tạo handle nhận **một Object[]**, trải hai phần tử ra để gọi `sum(int,int)`. Adapter được cấu hình **một lần** khi tạo handle; có thể gọi nó sau đó với descriptor `(Object[])int`:

~~~java
// Fragment từ chương trình đầy đủ:
MethodHandle spread = sum.asSpreader(Object[].class, 2);
int result = (int) spread.invokeExact(new Object[]{20, 22});
~~~

Vẫn có mảng đối số `Object[]` và các `Integer` cần unbox; adapter chủ yếu cho phép **chốt cách trải đối số trước** thay vì lựa chọn đường bridge tổng quát ở mỗi lần gọi.

`sum.asType(MethodType.methodType(Object.class, Object.class, Object.class))` lại tạo handle báo kiểu **(Object,Object)Object**, rồi có thể `invokeExact` với descriptor tương ứng. Cách này có thể phù hợp khi giao diện đầu vào **buộc phải Object**, nhưng vẫn không biến kiểu trả về thành primitive hay xóa bản chất boxing ở ranh giới.

## 5. Bẫy quan trọng: Object... của chính invokeWithArguments

Có **hai tầng varargs** khác nhau cần phân biệt:

1. `invokeWithArguments(Object... arguments)` dùng cú pháp varargs của **Java caller** để tạo/truyền danh sách `Object`.
2. **Handle đích** có thể là varargs collector hoặc một handle fixed-arity thông thường. Hai trường hợp này diễn giải đối số cuối khác nhau.

Điều này đặc biệt quan trọng khi đối số đích **bản thân là một array**.

### 5.1. Chương trình độc lập minh họa hình dạng đối số

Lưu file **ArgumentShapeDemo.java**:

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;

public class ArgumentShapeDemo {
    static String joinArray(String[] words) {
        return String.join("|", words);
    }
    static String prefixed(String prefix, String... words) {
        return prefix + "=" + String.join("|", words);
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodHandle arrayOnly = lookup.findStatic(
                ArgumentShapeDemo.class,
                "joinArray",
                MethodType.methodType(String.class, String[].class));
        System.out.println("arrayType=" + arrayOnly.type());
        System.out.println("oneArray="
                + arrayOnly.invokeWithArguments((Object) new String[]{"a", "b"}));
        try {
            arrayOnly.invokeWithArguments((Object[]) new String[]{"a", "b"});
        } catch (WrongMethodTypeException ex) {
            System.out.println("spreadMistake="
                    + ex.getClass().getSimpleName());
        }

        MethodHandle varargs = lookup.findStatic(
                ArgumentShapeDemo.class,
                "prefixed",
                MethodType.methodType(String.class, String.class, String[].class));
        System.out.println("varargsCollector=" + varargs.isVarargsCollector());
        System.out.println("variableCall="
                + varargs.invokeWithArguments("tag", "x", "y"));
        System.out.println("fixedArray="
                + varargs.asFixedArity().invokeWithArguments(
                        "tag", (Object) new String[]{"x", "y"}));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 ArgumentShapeDemo.java
java ArgumentShapeDemo
~~~

Stdout:

~~~text
arrayType=(String[])String
oneArray=a|b
spreadMistake=WrongMethodTypeException
varargsCollector=true
variableCall=tag=x|y
fixedArray=tag=x|y
~~~

### 5.2. Tại sao ép kiểu Object khác ép kiểu Object[]?

`joinArray(String[])` có handle fixed-arity, cần đúng **một tham số kiểu String[]**.

- `invokeWithArguments((Object) new String[]{"a", "b"})` yêu cầu Java tạo **một phần tử Object** chứa toàn bộ `String[]`, nên handle nhận đúng một array.
- `invokeWithArguments((Object[]) new String[]{"a", "b"})` truyền mảng `String[]` như chính **mảng các đối số** cho `Object...`; nó trở thành **hai đối số String**. Handle đích chỉ nhận một `String[]`, nên sai arity.

Đây là bẫy ở **Java varargs method call**, trước cả việc thực hiện chuyển đổi vào handle đích. Cú pháp `new Object[]{new String[]{"a", "b"}}` cũng diễn tả một đối số array tường minh.

Với `prefixed(String, String...)`, `findStatic` thường trả handle đang ở chế độ **varargs collector** vì method Java gốc là varargs. Khi dùng `invokeWithArguments("tag", "x", "y")`, handle có thể gom các từ thành `String[]` phù hợp. Khi muốn truyền **mảng đã có như một đối số array**, `asFixedArity()` giúp loại bỏ cách diễn giải varargs collector và lời gọi truyền `(Object) new String[]{...}` đúng một array.

Theo Javadoc, dạng `invokeWithArguments` trên varargs collector có quy tắc **thu gom mảng mới**, kể cả trong một số tình huống truyền array vốn trông đã phù hợp. Vì thế đừng dùng nó như giả định “mảng sẽ luôn được chuyển nguyên vẹn, không phải tạo mảng khác”.

## 6. “Cái giá của Object” gồm những gì?

Không có một con số overhead cố định cho mọi ứng dụng. Chi phí phụ thuộc bộ xử lý, JVM, JIT, luồng dữ liệu và cấu trúc handle. Nhưng có những điểm cần **nhìn thấy được trong hợp đồng lập trình**:

| Nguồn chi phí | Vì sao có thể xảy ra | Có thể giảm bằng cách nào? |
| --- | --- | --- |
| **Object[] / List → mảng** | Java varargs có thể cần mảng; List overload tạo array đại diện cho các phần tử | Dùng đường gọi có số đối số cố định nếu chữ ký đã biết; tái sử dụng cấu trúc phù hợp khi an toàn |
| **Boxing / unboxing primitive** | Primitive không thể nằm trực tiếp trong `Object[]`; kết quả primitive phải ra `Object` | Dùng `invokeExact` với descriptor primitive nếu có thể |
| **Chuyển đổi tham số** | Tham số ở ranh giới Object phải kiểm tra cast/unboxing/widening theo `MethodType` đích | Định kiểu và validate sớm; adapter ổn định như `asType` nếu hữu ích |
| **Thu gom varargs ở handle đích** | Varargs collector có thể tạo mảng cuối cùng khi nhận nhiều phần tử rời | `asFixedArity()` + truyền array rõ nếu đó là hợp đồng mong muốn |
| **Kiểm tra/định tuyến chung** | Danh sách runtime có nhiều độ dài/kiểu, gây ít thông tin tĩnh hơn cho optimizer | Cache handle/adapters theo chữ ký; hạn chế đa hình ở hot path |
| **Tách dữ liệu kết quả** | Caller nhận `Object`, phải cast/unbox khi dùng tiếp | Giữ kiểu trả về primitive/ref cụ thể trong đường gọi cố định |

Ví dụ, đoạn:

~~~java
// Fragment minh họa, giả sử mh có kiểu (int,int)int:
for (int i = 0; i < requests.size(); i++) {
    Object[] row = requests.get(i);       // Các giá trị đã là Object
    Object answer = mh.invokeWithArguments(row);
    consume(answer);
}
~~~

**Không phải chương trình độc lập**; `mh`, `requests`, `consume` là những thực thể minh họa. Nó có thể thích hợp nếu mỗi request có cấu trúc khác nhau, nhưng nếu tất cả đều là phép `sum(int,int)` trong một vòng lặp nóng, đường gọi trên bỏ qua cơ hội diễn đạt đối số/kết quả primitive một cách rõ ràng.

Đường có kiểu ổn định:

~~~java
// Fragment minh họa; mh có kiểu (int,int)int:
for (int i = 0; i < count; i++) {
    int answer = (int) mh.invokeExact(left[i], right[i]);
    sink += answer;
}
~~~

Đoạn này vẫn cần khai báo biến và xử lý `Throwable`, nhưng bộc lộ descriptor cố định **(int,int)int** cho JIT. Không cần chuyển mọi phần tử thành `Object` ngay tại biên gọi.

### 6.1. Có phải mỗi lần invokeWithArguments đều cấp phát mảng?

**Không được kết luận như vậy từ source.** Java varargs/List và các bước adaptation đặt ra cấu trúc, nhưng JVM có thể dùng escape analysis, inlining và các tối ưu khác để loại allocation trong các trường hợp cụ thể. Ngược lại, một đường gọi mang hình thái `Object[]` thật sự lưu/trao đổi với thành phần bên ngoài có thể không tối ưu giống đường gọi primitive tĩnh.

Chính vì thế, chỉ nên nói **có nguy cơ chi phí và mất thông tin kiểu**, không nói “chậm đúng N lần” nếu chưa đo trong workload thật.

### 6.2. Overhead đến từ cả nơi tạo dữ liệu, không chỉ invokeWithArguments

Ví dụ JSON parser tạo `List<Object>`; giá trị số có thể là `Integer`, `Long`, `Double` hoặc một kiểu khác tùy thư viện/cấu hình. Nếu không có schema, việc parse, validate, chuyển kiểu và dispatch đã là chi phí riêng. Thay một lời gọi `invokeWithArguments` bằng `invokeExact` không tự động loại tất cả các bước đó.

Một cách thiết kế thường tốt hơn là **chuẩn hóa dữ liệu ở ranh giới**:

~~~text
JSON / cấu hình / plugin input
    |
    v
validate schema + chuyển đổi giá trị có kiểm soát
    |
    +--> đường gọi động hiếm, dùng invokeWithArguments
    |
    +--> đường gọi lặp lại nhiều, dùng handle/adapters đã định kiểu và cache
~~~

## 7. Chọn API theo tình huống

### 7.1. Khi invokeWithArguments đáng dùng

- **Bridge runtime tổng quát:** gọi một handle từ hệ thống có mảng/list đối số nhưng không thể ghi call site tĩnh cho mọi MethodType.
- **Tooling và thử nghiệm:** trình chạy command, test harness, adapter giữa Reflection/JNI và MethodHandle.
- **Đường cấu hình động không quá nóng:** mỗi request có tên thao tác hoặc arity khác nhau, và chi phí parsing/network/I/O thường lớn hơn chi phí gọi.
- **Prototype:** cần tính linh hoạt và khả năng quan sát, trước khi tối ưu một đường gọi cụ thể.

Trong những tình huống này, tính đúng đắn của **schema, số đối số, kiểu dữ liệu, xử lý lỗi** quan trọng hơn kỳ vọng tối ưu vi mô.

### 7.2. Khi nên dùng invokeExact hoặc invoke

Nếu handle và danh sách tham số **ổn định** trong một loop/call site, hãy cân nhắc:

~~~java
// Fragment: mh.type() phải bằng methodType(int.class,int.class,int.class).
int value = (int) mh.invokeExact(20, 22);
~~~

`invokeExact` cho JVM descriptor cố định, không yêu cầu tự động chuyển `Object` thành primitive tại ranh giới này. Nếu kiểu ở call site được xác định tĩnh nhưng cần chuyển đổi hợp lệ, `invoke` cho phép thích nghi với `MethodType` đích theo luật `asType`.

**Không chọn `invokeExact` chỉ vì chữ “Exact” nghe nhanh.** Nếu phải làm nhiều phép cast/boxing ở trước call site hoặc handle thay kiểu liên tục, tổng hiệu năng còn tùy thiết kế.

### 7.3. Khi nên chuẩn bị adapter một lần

`asType` tạo handle có MethodType mới; `asSpreader` biến nhiều đối số cuối thành một mảng; `asCollector` biến một mảng cuối thành một số đối số tường minh. Chúng giúp mô tả **hợp đồng adaptation ổn định** từ trước, thay vì để mỗi lời gọi xử lý lại hoàn cảnh hoàn toàn tổng quát.

Ví dụ:

~~~java
// Fragment: mh là (int,int)int.
MethodHandle spread = mh.asSpreader(Object[].class, 2);
// spread.type() là (Object[])int.
int result = (int) spread.invokeExact(new Object[]{20, 22});
~~~

Adapter dạng này vẫn phải nhận một mảng `Object[]`. Nó **không triệt tiêu boxing** của giá trị số trong mảng, nhưng giữ được kiểu trả về `int` và xác định cố định phép spread. Nếu thao tác dùng lại nhiều lần, hãy khởi tạo và kiểm tra adapter sớm, lưu theo chữ ký hợp lệ.

Một trường hợp khác là giao diện gọi cố định nhận `Object, Object` và trả `Object`:

~~~java
// Fragment: mh là (int,int)int.
MethodHandle objectHandle = mh.asType(
        MethodType.methodType(Object.class, Object.class, Object.class));
Object result = (Object) objectHandle.invokeExact(
        (Object) Integer.valueOf(20), (Object) Integer.valueOf(22));
~~~

Đây là lời gọi `invokeExact` **trên adapter có kiểu Object**, không phải lời gọi primitive exact. Cần nhận diện ranh giới nào thực sự còn boxing trước khi kỳ vọng hiệu năng.

### 7.4. Nếu có nhiều handle do cấu hình

Thay vì gọi `findStatic`/`findVirtual` và dựng adapter trên mọi request, có thể xây **registry** từ khóa operation/chữ ký đã được cho phép tới handle được cache. Cần lưu ý danh tính class/class loader và vòng đời plugin: không giữ vô thời hạn handle tham chiếu vào loader đã hết hạn.

Nếu hệ thống không tin cậy đầu vào, đừng để request tùy ý chọn class/method chỉ qua tên. Ánh xạ command hợp lệ vào tập MethodHandle được phê duyệt, validate số và kiểu dữ liệu trước khi gọi.

## 8. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `WrongMethodTypeException` | Số đối số không phù hợp fixed-arity hoặc không thể điều chỉnh MethodType | In `handle.type()`, kiểm tra arity và chế độ varargs collector |
| `ClassCastException` | Giá trị Object không thể cast/unbox sang kiểu đích | Kiểm tra runtime class và schema; không giả định chuỗi số tự parse |
| `NullPointerException` khi tham số primitive | Unboxing một đối số null | Từ chối null hoặc định nghĩa giá trị mặc định rõ ràng ở tầng schema |
| Truyền một `String[]` mà thành hai đối số | Cách gọi Java `Object...` trải array thành argument array | Cast thành `Object` khi muốn một array; hoặc dùng `new Object[]{array}` |
| Handle varargs thu gom không như dự kiến | `isVarargsCollector()==true` và đường gọi generic có thể collect lại | Dùng `asFixedArity()` khi truyền array như một tham số cuối cố định |
| Instance method không được gọi | Thiếu receiver ở đối số đầu | Kiểm tra `handle.type()`; có thể dùng `bindTo(receiver)` |
| Giá trị trả về là `Integer` nhưng muốn `int` | `invokeWithArguments` trả `Object` | Cast/unbox an toàn; cân nhắc typed call |
| Method đích ném ngoại lệ | `throws Throwable` truyền lỗi từ target | Xử lý đúng ngoại lệ nghiệp vụ, không nhầm với lỗi adaptation |

Có thêm một khác biệt cần nhớ: `java.lang.reflect.Method.invoke` thường bao bọc ngoại lệ của method đích trong `InvocationTargetException`. `MethodHandle.invokeWithArguments` không áp đặt lớp bao như vậy; hãy quản lý `Throwable` dựa vào hợp đồng method đích.

## 9. Đo hiệu năng thế nào cho đúng?

Nếu quyết định tối ưu dựa trên throughput hoặc latency, đo với **JMH** hoặc một thiết kế benchmark có warm-up và cơ chế chống tối ưu bỏ công việc. Các nguyên tắc:

1. So sánh **cùng một hành vi nghiệp vụ, cùng dữ liệu và kiểu kết quả**.
2. Tách chi phí **lookup/tạo adapter** khỏi chi phí **gọi nhiều lần**, nếu adapter được cache trong ứng dụng thật.
3. Đo cả đường pipeline (parse dữ liệu, boxing, validation, dispatch) khi đó mới là nơi ứng dụng tốn CPU.
4. Tránh benchmark vòng lặp quá đơn giản có constant folding hoặc dead-code elimination; tiêu thụ kết quả bằng công cụ phù hợp.
5. Xem xét phân phối request, tần suất thay đổi handle, JVM/JDK, JIT warm-up và GC/allocation.
6. Báo cả hiệu năng lẫn mức độ đúng đắn: một cách gọi nhanh nhưng bỏ qua validation hoặc xử lý sai varargs là không tương đương.

**Không dùng stdout hay thời gian chạy một lần của hai demo phía trên để kết luận performance.** Chúng xác nhận **ngữ nghĩa**, không phải microbenchmark.

## 10. Bài tập tự kiểm tra

**Câu 1.** Handle có kiểu `(int,int)int`. Vì sao `invokeWithArguments(20,22)` trả `Integer` dưới dạng `Object`?

**Đáp án:** API tổng quát trả `Object`, trong khi method đích trả primitive `int`; kết quả cần biểu diễn qua wrapper `Integer`.

**Câu 2.** Vì sao `invokeWithArguments("20",22)` không thay `"20"` thành số `20`?

**Đáp án:** Conversion của handle cho phép reference cast, unboxing/widening thích hợp; nó không phải parser text. Với `int` đích, `String` không có conversion hợp lệ.

**Câu 3.** Muốn gọi fixed-arity handle nhận một `String[]`, bạn sẽ dùng `invokeWithArguments((Object) arr)` hay `invokeWithArguments((Object[]) arr)`?

**Đáp án:** Dùng `(Object) arr` hoặc `new Object[]{arr}` để truyền **một đối số String[]**. Dạng `(Object[]) arr` đưa các phần tử của arr thành danh sách đối số.

**Câu 4.** `invokeExact` chỉ cần trùng số tham số, còn kiểu trả về tùy ý được không?

**Đáp án:** Không. Descriptor của call site `invokeExact` gồm **cả kiểu trả về** và phải trùng `handle.type()`.

**Câu 5.** Vì sao `asSpreader(Object[].class,2)` chưa chắc loại hết chi phí đường Object?

**Đáp án:** Nó cố định thao tác trải mảng thành hai đối số; input vẫn là `Object[]` và có thể cần boxing/unboxing cho primitive.

**Câu 6.** Gặp một hệ thống RPC nhận `List<Object>` với số đối số thay đổi nhưng tần suất thấp; có nhất thiết tránh `invokeWithArguments` không?

**Đáp án:** Không. Đây là trường hợp bridge động phù hợp, miễn schema/arity/loại đối số được validate và xử lý lỗi rõ ràng. Chỉ đổi sang typed handle khi tính ổn định và chi phí đo được biện minh.

**Câu 7.** Tại sao không thể nói chính xác `invokeWithArguments` chậm N lần từ bảng chi phí?

**Đáp án:** JVM có thể tối ưu mảng/boxing/adapter; chi phí còn tùy khả năng inline, call site, dữ liệu và workload. Cần benchmark đáng tin.

## Ghi nhớ

- `invokeWithArguments` là đường gọi tổng quát cho **danh sách đối số runtime**, nhận các đối số như `Object` và trả **`Object`**.
- Khi handle đích dùng primitive, có thể phải **unbox input và box output**; việc chuyển đổi kiểu không thay thế bước parse/validate dữ liệu.
- `Object...` của **chính invokeWithArguments** và **varargs collector của handle đích** là hai tầng khác nhau; array có thể bị trải hoặc thu gom ngoài ý muốn.
- `invokeExact` đòi descriptor chính xác gồm cả return type; `invoke` thích nghi từ descriptor của call site; `invokeWithArguments` linh hoạt nhất khi chỉ có `Object[]` hoặc `List`.
- Khi lời gọi có chữ ký ổn định và tần suất cao, ưu tiên **typed call hoặc adapter được chuẩn bị/cached**, rồi đo workload thật trước khi kết luận.
- Mọi đường gọi vẫn phải kiểm tra quyền tạo handle, số/kiểu đối số và ngoại lệ từ method đích.

## Tài liệu tham khảo

- Java SE 17, **MethodHandle**, đặc biệt `invokeWithArguments`, `invoke`, `invokeExact`, `asType`, `asSpreader` và `asFixedArity`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html
- Java SE 17, **MethodType**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html
- Java SE 17, **MethodHandles.Lookup**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html
- OpenJDK JMH (microbenchmark harness): https://github.com/openjdk/jmh
