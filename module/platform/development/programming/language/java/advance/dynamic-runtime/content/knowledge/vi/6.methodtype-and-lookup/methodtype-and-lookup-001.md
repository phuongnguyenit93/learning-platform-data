# 6.1 MethodHandle là tham chiếu thực thi có kiểu; phân biệt với Method

Trong Java, `java.lang.invoke.MethodHandle` đại diện cho **một khả năng gọi đã được liên kết với thao tác cụ thể**, có **chữ ký kiểu đầy đủ ở thời điểm chạy**. Ta có thể giữ nó trong biến, truyền như giá trị, gọi nhiều lần, gắn sẵn đối tượng nhận (*receiver*), hoặc tạo một handle mới có chữ ký thích nghi với ngữ cảnh. Đối tượng `java.lang.reflect.Method` trong Reflection cũng mô tả phương thức và có thể gọi nó, nhưng là một **đối tượng metadata về khai báo phương thức**, với cơ chế gọi và hợp đồng kiểu khác hẳn.

Bài này tập trung vào bản chất của `MethodHandle`, vai trò trực tiếp của `MethodType` và `MethodHandles.Lookup`, cú pháp gọi `invokeExact`/`invoke`, cách so sánh với `Method.invoke` và những lỗi dễ gặp. Tất cả ví dụ chạy được dùng **Java 17+**.

## 1. MethodHandle trỏ đến một thao tác gọi được

Hãy bắt đầu bằng ý tưởng:

~~~java
// Minh họa khái niệm, chưa phải chương trình hoàn chỉnh:
MethodHandle handle = /* tìm được handle hợp lệ */;
String result = (String) handle.invokeExact(/* tham số đúng kiểu */);
~~~

`MethodHandle` không lưu đơn thuần “tên phương thức + danh sách tham số”; nó gắn với **một hành vi có thể thực thi** đã được nhận diện, chẳng hạn:

- Gọi phương thức `static`.
- Gọi phương thức instance theo cơ chế virtual dispatch.
- Gọi constructor để tạo instance.
- Đọc hoặc ghi field.
- Gọi một handle khác với tham số đã gắn sẵn, đã hoán đổi, đã lọc hoặc đã chuyển đổi kiểu.

Method handle thường nhận được qua `MethodHandles.Lookup`. Khi việc tìm kiếm thành công, kết quả có một **`MethodType`** cố định mô tả cả kiểu tham số lẫn kiểu trả về. Từ “có kiểu” ở đây nghĩa là **chữ ký JVM được mô tả và kiểm tra tại call site**. Nó không có nghĩa biến Java được khai báo thành `MethodHandle<String, Integer>`; `MethodHandle` không phải một generic class.

Một handle có thể tham chiếu phương thức được khai báo bằng generic, nhưng `MethodType` sử dụng **runtime classes sau erasure** (`Class<?>`), không lưu trực tiếp `List<String>` hoặc `<T>`. Khi cần metadata generic đầy đủ của khai báo, `Method` và các API `getGeneric...()` phục vụ mục tiêu đó.

## 2. Ba thành phần: Lookup → MethodHandle → MethodType

Luồng thường gặp:

~~~text
Class + tên thao tác + MethodType
              │
              ▼
       MethodHandles.Lookup
              │ findStatic / findVirtual / findConstructor ...
              ▼
       MethodHandle đã được liên kết
              │
              ├── type() → MethodType của handle
              ├── invokeExact(...) → gọi theo chữ ký khớp tuyệt đối
              ├── invoke(...)      → cho phép chuyển kiểu được hỗ trợ
              └── asType/bindTo/... → tạo handle mới đã thích nghi
~~~

**`MethodHandles.Lookup`** là đối tượng có quyền tìm và tạo handle theo ngữ cảnh truy cập. `MethodHandles.lookup()` tạo lookup đại diện cho lớp đang gọi; quyền truy cập không thể tùy tiện nâng lên. `MethodHandles.publicLookup()` chỉ dùng cho thành viên public có thể truy cập được trong ngữ cảnh lookup đó. Với thành viên private của lớp khác, việc có thể dùng `privateLookupIn` phụ thuộc quyền truy cập và ranh giới module (đặc biệt quy tắc `opens`/`exports`).

**`MethodType`** mô tả chính xác **kiểu trả về** và **các kiểu tham số** của lời gọi. Ví dụ:

~~~java
MethodType oneString = MethodType.methodType(String.class, String.class);
MethodType addInts   = MethodType.methodType(int.class, int.class, int.class);
MethodType noResult  = MethodType.methodType(void.class, String.class);
~~~

Theo thứ tự, chúng mô tả `(String)String`, `(int,int)int` và `(String)void`. Một `MethodType` chỉ là mô tả chữ ký; **nó không tự tìm hay gọi phương thức**. `methodType(...)` nhận các đối tượng `Class<?>`; kiểu nguyên thủy như `int.class` và `void.class` hoàn toàn hợp lệ.

**`MethodHandle`** là đối tượng giữ thao tác và chữ ký. `handle.type()` lấy `MethodType` của handle sau khi tìm hoặc biến đổi. Một handle có kiểu `(String)String` có thể được gọi theo `invokeExact` nếu tham số và kiểu trả về tại call site khớp đúng kiểu này.

## 3. Chữ ký lookup khác với chữ ký của handle instance

Giả sử:

~~~java
class Greeter {
    public String greet(String name) {
        return "Hello " + name;
    }

    public static String upper(String text) {
        return text.toUpperCase(java.util.Locale.ROOT);
    }
}
~~~

Tìm static method:

~~~java
MethodHandles.Lookup lookup = MethodHandles.lookup();
MethodType signature = MethodType.methodType(String.class, String.class);

MethodHandle staticHandle =
        lookup.findStatic(Greeter.class, "upper", signature);
// staticHandle.type(): (String)String
~~~

Tìm instance method:

~~~java
MethodHandle virtualHandle =
        lookup.findVirtual(Greeter.class, "greet", signature);
// virtualHandle.type(): (Greeter,String)String
~~~

Đây là chỗ người mới thường nhầm:

- Khi gọi `findVirtual(Greeter.class, "greet", signature)`, `signature` chứa **tham số được khai báo của phương thức**, chưa chứa `this`. Phương thức `greet(String)` khai báo một tham số `String`.
- Handle trả về cần **receiver** là tham số đầu: `(Greeter,String)String`. Vì vậy call site phải truyền `Greeter` trước, rồi đến `String`.
- Với static method không có receiver, handle vẫn là `(String)String`.
- `findVirtual` thực hiện **virtual dispatch** theo kiểu runtime của receiver, nên nếu có subclass override phương thức, hành vi gọi vẫn tuân theo quy tắc dispatch thích hợp của JVM.

Khác biệt này xuất hiện ở constructor và field nữa:

| Lookup API | Kiểu dùng khi tìm | `handle.type()` sau khi tìm |
| --- | --- | --- |
| `findStatic(C, "f", methodType(R.class, P.class))` | Ký hiệu `(P)R` | `(P)R` |
| `findVirtual(C, "f", methodType(R.class, P.class))` | Ký hiệu `(P)R` | `(C,P)R`, có receiver |
| `findConstructor(C, methodType(void.class, P.class))` | Ký hiệu constructor `(P)void` | `(P)C`, trả instance |
| `findGetter(C, "field", F.class)` | Tên field + kiểu field | `(C)F` |
| `findStaticGetter(C, "field", F.class)` | Tên static field + kiểu field | `()F` |

Trong bảng, `C`, `P`, `R`, `F` là ký hiệu cho **các class/kiểu tương ứng**, không phải code Java đầy đủ để sao chép. Với constructor, lookup sử dụng `void.class` vì constructor không có kiểu trả về ở chữ ký khai báo; handle tạo được lại trả instance của `C`.

## 4. invokeExact: khớp chính xác tham số và kiểu trả về

`invokeExact` là phương thức **signature-polymorphic**. Kiểu tham số và kiểu trả về của lời gọi được xác định từ chính biểu thức gọi trong bytecode, sau đó phải khớp **toàn bộ** `handle.type()` tại runtime.

Giả sử handle có kiểu `(String)String`:

~~~java
String text = (String) handle.invokeExact("Java");
~~~

Đây là call site `(String)String`. Nếu đổi thành:

~~~java
Object value = handle.invokeExact("Java");
~~~

call site bây giờ là `(String)Object` vì kiểu trả về mong đợi là `Object`. Dù `String` là subtype của `Object`, **`invokeExact` không tự chuyển đổi kiểu trả về**, nên sẽ ném `WrongMethodTypeException` khi handle thực tế vẫn là `(String)String`.

Các quy tắc quan trọng:

1. Cả **kiểu đối số** lẫn **kiểu kết quả** phải chính xác. Ép kiểu ở vị trí gọi, ví dụ `(String) handle.invokeExact(...)`, có ý nghĩa để xác định return type của call site.
2. Với handle nhận `int`, tham số `Integer` hay `long` không tự thay thế `int` cho `invokeExact`.
3. Lời gọi có thể **biên dịch thành công** dù chữ ký không khớp với handle đang có trong biến, vì compiler không biết `handle.type()` qua một biến `MethodHandle` tổng quát. Sai lệch bị phát hiện lúc chạy.
4. `invokeExact` không sử dụng dạng `Object...` của `Method.invoke`; các tham số trong lời gọi là tham số thực của method type, do JVM hỗ trợ call site signature-polymorphic.

Nếu handle có return type `void`, cần gọi phù hợp với chữ ký trả về `void` (một statement không gán kết quả). Đừng cố ép mọi lời gọi thành nhận `Object`.

## 5. invoke: chuyển đổi kiểu được hỗ trợ

`invoke` cũng là phương thức signature-polymorphic nhưng **cho phép thích nghi** call site tới `handle.type()` thông qua các phép chuyển đổi được `asType` hỗ trợ. Ví dụ từ handle `(String)String`:

~~~java
Object input = "Java";
Object output = handle.invoke(input); // call site: (Object)Object
~~~

Ở runtime, adapter chuyển `Object` đầu vào sang `String` bằng kiểm tra/cast và trả `String` dưới dạng `Object`. Nếu `input` là `Integer`, có thể xuất hiện `ClassCastException`. Với primitive, adapter cũng có thể dùng boxing/unboxing và widening phù hợp, nhưng `invoke` **không chuyển tùy ý chuỗi "42" thành số 42**.

Có thể thích nghi **tường minh** một lần qua:

~~~java
MethodType generic = MethodType.methodType(Object.class, Object.class);
MethodHandle adapted = handle.asType(generic);
Object result = adapted.invokeExact((Object) "Java");
~~~

`adapted.type()` là `(Object)Object` và `invokeExact` lúc này khớp chữ ký của **handle mới**. `asType` không thay thế logic của phương thức gốc: nó tạo một handle thực hiện chuyển đổi vào/ra xung quanh thao tác ban đầu; nếu không thể thích nghi kiểu, việc tạo hoặc gọi adapter có thể thất bại.

**Ranh giới:** `invoke` thường phù hợp khi cần linh hoạt kiểu, còn `invokeExact` rõ ràng hơn khi đã biết chính xác chữ ký và muốn tránh chuyển đổi ngầm. Không suy ra một phương thức “luôn nhanh hơn” chỉ từ tên của chúng; hiệu năng còn phụ thuộc JIT, mô hình gọi và cách ứng dụng cache handle.

## 6. Ví dụ hoàn chỉnh: tìm, gọi, gắn receiver và đối chiếu với Method

Tạo file **HandleVsMethodDemo.java**:

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;
import java.lang.reflect.Method;
import java.util.Locale;

public class HandleVsMethodDemo {
    static class Greeter {
        private final String prefix;

        Greeter(String prefix) {
            this.prefix = prefix;
        }

        public String greet(String name) {
            return prefix + " " + name;
        }

        public static String upper(String text) {
            return text.toUpperCase(Locale.ROOT);
        }
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodType oneString =
                MethodType.methodType(String.class, String.class);

        MethodHandle virtual =
                lookup.findVirtual(Greeter.class, "greet", oneString);

        Greeter greeter = new Greeter("Hello");
        System.out.println("handle params: " +
                virtual.type().parameterCount());
        System.out.println("handle return: " +
                virtual.type().returnType().getSimpleName());

        String exact = (String) virtual.invokeExact(greeter, "Ada");
        System.out.println("exact: " + exact);

        // bindTo gắn receiver, tạo handle (String)String.
        MethodHandle bound = virtual.bindTo(greeter);
        System.out.println("bound params: " +
                bound.type().parameterCount());

        String boundResult = (String) bound.invokeExact("Minh");
        System.out.println("bound: " + boundResult);

        // invoke có thể chuyển Object -> String tại runtime.
        Object input = "Linh";
        Object flexible = bound.invoke(input);
        System.out.println("invoke: " + flexible);

        MethodHandle adapted = bound.asType(
                MethodType.methodType(Object.class, Object.class));
        Object adaptedResult = adapted.invokeExact((Object) "Nhi");
        System.out.println("asType: " + adaptedResult);

        MethodHandle upper =
                lookup.findStatic(Greeter.class, "upper", oneString);
        String upperResult = (String) upper.invokeExact("java");
        System.out.println("static: " + upperResult);

        try {
            // Return type Object != String: invokeExact không thích nghi.
            Object incompatible = bound.invokeExact("Bao");
            System.out.println(incompatible);
        } catch (WrongMethodTypeException expected) {
            System.out.println("invokeExact: WrongMethodTypeException");
        }

        // Reflection Method mô tả khai báo và trả Object khi invoke.
        Method reflected = Greeter.class.getDeclaredMethod(
                "greet", String.class);
        Object reflectedResult = reflected.invoke(greeter, "Mai");
        System.out.println("Method.invoke: " + reflectedResult);

        // Chuyển Method thành MethodHandle (vẫn phải có quyền truy cập).
        MethodHandle fromReflection = lookup.unreflect(reflected);
        String converted = (String) fromReflection.invokeExact(
                greeter, "Thu");
        System.out.println("unreflect: " + converted);
    }
}
~~~

Biên dịch và chạy từ thư mục chứa file:

~~~bash
javac HandleVsMethodDemo.java
java HandleVsMethodDemo
~~~

Kết quả stdout dự kiến:

~~~text
handle params: 2
handle return: String
exact: Hello Ada
bound params: 1
bound: Hello Minh
invoke: Hello Linh
asType: Hello Nhi
static: JAVA
invokeExact: WrongMethodTypeException
Method.invoke: Hello Mai
unreflect: Hello Thu
~~~

**Giải thích theo từng giai đoạn:**

- `findVirtual` nhận chữ ký phương thức `(String)String` nhưng tạo handle có **hai tham số**: receiver `Greeter` và `String`. Kiểu trả về là `String.class`.
- `invokeExact(greeter, "Ada")` có kiểu call site `(Greeter,String)String`. Việc ép `(String)` trên kết quả giữ return type chính xác.
- `bindTo(greeter)` tạo handle mới đã giữ receiver, chuyển chữ ký sang `(String)String`; handle ban đầu không đổi.
- `bound.invoke(input)` nhận biến có static type `Object`, chuyển sang `String` tại runtime và trả kết quả dưới dạng `Object`.
- `asType` thay đổi chữ ký nhìn từ call site sang `(Object)Object`; nhờ đó `adapted.invokeExact((Object) "Nhi")` là lời gọi *exact* đối với handle đã thích nghi.
- `findStatic` không có receiver; gọi trực tiếp với `"java"` cho `"JAVA"`.
- Trong nhánh lỗi, Java xác định kiểu trả về là `Object` vì có biến nhận `Object incompatible`. Handle cần trả `String`, nên `invokeExact` ném `WrongMethodTypeException` trước khi thực thi phương thức đích.
- `Method.invoke` đi qua API Reflection và trả `Object`; `lookup.unreflect(reflected)` tạo một handle tương ứng với method có sẵn để có thể sử dụng cơ chế gọi của MethodHandle.

Cần nhớ rằng **`bindTo` chỉ gắn tham số tham chiếu ở vị trí đầu của handle**. Với trường hợp cần gắn tham số ở vị trí khác hoặc kiểu primitive, công cụ tương ứng là `MethodHandles.insertArguments`. Adapter không buộc phải làm thay đổi method gốc.

## 7. Method và MethodHandle giống nhau ở đâu, khác nhau ở đâu?

`Method` là `java.lang.reflect.Method`. Khi gọi:

~~~java
Method method = Greeter.class.getDeclaredMethod("greet", String.class);
Object result = method.invoke(greeter, "Lan");
~~~

`Method` có các API metadata: `getName()`, `getDeclaringClass()`, `getModifiers()`, `getParameterTypes()`, `getGenericParameterTypes()`, `getReturnType()`, `getGenericReturnType()`, `getAnnotations()`... Nó phù hợp khi ứng dụng cần **khám phá một khai báo** hoặc framework cần đọc annotation, generic signature và quy tắc truy cập. `Method.invoke` nhận receiver (hoặc `null` cho static method) cùng `Object... args`, thực hiện kiểm tra/boxing-unboxing cần thiết và trả `Object` (hoặc `null` nếu method trả `void`).

`MethodHandle` tập trung vào **cách thực thi**. Nó có `type()` và một bộ combinator/adapters như `asType`, `bindTo`, `filterArguments`, `filterReturnValue`, `guardWithTest`...; nhưng không cung cấp trực tiếp đầy đủ API `getAnnotations()` hoặc generic declaration metadata như `Method`. Một handle có thể do combinator tạo ra và không còn tương ứng với **một phương thức khai báo duy nhất**.

| Tiêu chí | `java.lang.reflect.Method` | `java.lang.invoke.MethodHandle` |
| --- | --- | --- |
| Bản chất | Metadata của một phương thức được khai báo | Tham chiếu tới hành vi có thể gọi (có thể kết hợp/biến đổi) |
| Chữ ký trong object | Tên, declaring class, parameter/return types, modifiers, generic metadata | `MethodType`: kiểu trả về và tham số tại runtime |
| Cách gọi chính | `method.invoke(receiver, Object... args)` | `handle.invokeExact(args...)` hoặc `handle.invoke(args...)` |
| Kiểu tham số ở call site | Được đóng gói trong `Object...` | Phản ánh chữ ký call site, được JVM kiểm tra/thích nghi |
| Kết quả gọi | `Object` (boxing primitive; `null` cho void) | Theo return type của call site; có thể là primitive hoặc void |
| Instance receiver | Receiver là đối số riêng của `Method.invoke` | Receiver thường là tham số đầu của handle instance chưa bound |
| Ngoại lệ do phương thức đích ném | Bọc trong `InvocationTargetException` | Lan truyền trực tiếp `Throwable` từ đích |
| Kiểm soát truy cập | Quyền truy cập Reflection khi gọi và cấu hình accessibility | Lookup kiểm tra quyền khi tạo handle; có thể cấp quyền gọi qua handle đã tạo |
| Generic/annotation metadata | Có API `getGeneric...`, `getAnnotations` | Không cung cấp toàn bộ metadata của khai báo |
| Biến đổi/chắp nối lời gọi | Không có bộ combinator chuyên biệt | `bindTo`, `asType`, `filterArguments`, `guardWithTest`... |
| Hiệu năng | Phụ thuộc triển khai, tần suất, JIT | Có thể được JIT tối ưu rất tốt khi handle ổn định; cần benchmark |
| Tình huống hay gặp | Khám phá API, annotations, framework metadata | Dynamic dispatch, adapter, language runtime, linkage/call site |

**Không đối chiếu một-một:** `MethodHandle` còn biểu diễn constructor, field access và nhiều chuỗi xử lý được kết hợp; `Method` chỉ là metadata của method. Nếu cần đối tượng Method từ handle, `MethodHandles.reflectAs(...)` có thể hỗ trợ một số **direct method handles** khi có quyền phù hợp, nhưng không thể mặc định biến mọi handle kết hợp thành một `Method` tương đương.

## 8. Ngoại lệ khác nhau: target exception và wrapper

Một khác biệt rất thực tế là cách ngoại lệ của phương thức đích xuất hiện:

- `Method.invoke(...)` bao lỗi do code bên trong method đích ném trong `java.lang.reflect.InvocationTargetException`. Muốn biết nguyên nhân gốc, dùng `getCause()` hoặc `getTargetException()`.
- `MethodHandle.invokeExact(...)` và `invoke(...)` cho ngoại lệ của target **đi trực tiếp** ra caller, không bọc trong `InvocationTargetException` chỉ vì cơ chế gọi.
- Lỗi **trước khi gọi đích** có thể là `WrongMethodTypeException` (chữ ký không khớp / không thích nghi được) hoặc `ClassCastException` khi adapter cần cast một giá trị không tương thích.
- `Lookup.findVirtual/findStatic` có thể ném `NoSuchMethodException` hoặc `IllegalAccessException` khi tên/chữ ký không tồn tại hoặc thiếu quyền; khác với ngoại lệ của target lúc thực thi.

Ví dụ độc lập thứ hai, file **HandleExceptionDemo.java**:

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

public class HandleExceptionDemo {
    public static class Calculator {
        public int base = 10;

        public Calculator() {
        }

        public int divide(int numerator, int denominator) {
            return numerator / denominator;
        }
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        MethodHandle constructor = lookup.findConstructor(
                Calculator.class, MethodType.methodType(void.class));
        Calculator calculator = (Calculator) constructor.invokeExact();

        MethodHandle getter =
                lookup.findGetter(Calculator.class, "base", int.class);
        int base = (int) getter.invokeExact(calculator);
        System.out.println("getter: " + base);

        MethodHandle divide = lookup.findVirtual(
                Calculator.class,
                "divide",
                MethodType.methodType(int.class, int.class, int.class));

        try {
            int ignored = (int) divide.invokeExact(calculator, 8, 0);
            System.out.println(ignored);
        } catch (ArithmeticException ex) {
            System.out.println("handle: ArithmeticException");
        }

        Method method = Calculator.class.getMethod(
                "divide", int.class, int.class);

        try {
            method.invoke(calculator, 8, 0);
        } catch (InvocationTargetException ex) {
            System.out.println("method wrapper: " +
                    ex.getClass().getSimpleName());
            System.out.println("target: " +
                    ex.getCause().getClass().getSimpleName());
        }
    }
}
~~~

~~~bash
javac HandleExceptionDemo.java
java HandleExceptionDemo
~~~

Stdout dự kiến:

~~~text
getter: 10
handle: ArithmeticException
method wrapper: InvocationTargetException
target: ArithmeticException
~~~

Ở đây `findConstructor` nhận chữ ký constructor không có tham số và **return type `void.class` khi lookup**, nhưng handle kết quả có kiểu `()Calculator`. `findGetter` tạo handle kiểu `(Calculator)int`. `findVirtual` với method `divide(int,int)` tạo handle `(Calculator,int,int)int`. Khi mẫu số bằng 0, phần chia nguyên ném `ArithmeticException`: lời gọi handle nhận ngoại lệ này trực tiếp; `Method.invoke` bọc ngoại lệ gốc trong `InvocationTargetException`.

Cả hai chương trình sử dụng `main(String[] args) throws Throwable` vì các phương thức gọi trên `MethodHandle` có hợp đồng `throws Throwable` rộng hơn `throws Exception`. Khi xây ứng dụng thực tế, xử lý những loại ngoại lệ cần thiết theo ngữ cảnh, thay vì bắt `Throwable` rồi bỏ qua toàn bộ lỗi JVM.

## 9. Cách Lookup cấp quyền và vì sao không giống setAccessible

`MethodHandles.Lookup` thể hiện **ngữ cảnh quyền truy cập của caller**. Các lệnh như `findStatic`, `findVirtual`, `findConstructor`, `findGetter` sẽ thực hiện tra cứu và kiểm tra quyền tương ứng. Nếu thành viên không tồn tại đúng tên/chữ ký, có thể gặp `NoSuchMethodException`; nếu không đủ quyền hoặc không thể truy cập do module, có thể gặp `IllegalAccessException`.

Không nhầm `lookup()` với đặc quyền toàn JVM: lookup của một class thông thường không tự có quyền gọi private member của class bất kỳ. `privateLookupIn(Target.class, lookup)` cho phép xin lookup có quyền private vào class đích **khi ngữ cảnh và module cho phép**; nó không phá ranh giới module tùy ý. `publicLookup()` hữu ích khi chỉ cần thao tác với API public truy cập được.

Với Reflection, `Method#setAccessible(true)` hoặc `trySetAccessible()` có thể điều chỉnh kiểm tra quyền trong phạm vi hợp lệ, nhưng vẫn chịu quy tắc của Java Platform Module System. `Lookup` kiểm soát quá trình **tạo handle**; sau khi tạo thành công, handle có thể được truyền như một khả năng gọi đã được liên kết, và người nhận có thể gọi nó mà không phải lặp lại toàn bộ thao tác tìm kiếm. Vì vậy, **không phát tán handle đã có quyền nhạy cảm cho mã không tin cậy**.

Nếu chuyển từ `Method` sang `MethodHandle` bằng `lookup.unreflect(method)`, quyền truy cập vẫn quan trọng; việc có đối tượng `Method` không mặc nhiên cho quyền tạo handle tới mọi private method.

## 10. handle.type(), generic và ép kiểu: ba lớp khái niệm phải tách biệt

**Lớp 1 — Chữ ký Java trong source:** `String greet(String who)` là khai báo. Nếu có `<T> T transform(T input)`, đây là generic method; biến kiểu `T` có ý nghĩa ở trình biên dịch và metadata.

**Lớp 2 — JVM `MethodType`:** Sau erasure, `<T> T transform(T input)` (không có bound) có kiểu thực thi gần với `(Object)Object`. `MethodType` giữ `Class<?>`/primitive return và parameter; không giữ `T` trong `MethodHandle.type()`. Với `T extends Number`, erasure của `T` thường là `Number`, nên kiểu JVM tương ứng dựa theo `Number`.

**Lớp 3 — Call-site signature:** `invokeExact` diễn giải kiểu đối số và kết quả của biểu thức gọi hiện tại. Nó phải khớp **handle type**, không căn cứ vào generic type inference riêng của `Method`. `invoke` có thể thích nghi theo quy tắc `asType`; adapter không phải cơ chế suy luận generic đầy đủ.

Ví dụ `Method` có thể cho biết `List<String>` ở `getGenericReturnType()`, trong khi một handle gọi method đó chỉ có thể ghi return type là `List.class` hoặc một kiểu runtime tương đương theo chữ ký erased. Đừng dùng `handle.type().toString()` để suy diễn generic argument đã bị xóa.

## 11. Lưu handle, bind receiver và chia sẻ adapter đúng cách

`MethodHandle` là object có thể giữ trong field và dùng nhiều lần. Chữ ký `type()` của một handle ổn định; các phép biến đổi như `asType` hoặc `bindTo` **trả về handle mới**, không sửa chữ ký của handle ban đầu.

Ví dụ thao tác trên handle instance `(Greeter,String)String`:

~~~java
// Giả định virtual và greeter đã được tạo như chương trình ở trên.
MethodHandle bound = virtual.bindTo(greeter);
// bound.type(): (String)String

MethodHandle generic = bound.asType(
        MethodType.methodType(Object.class, Object.class));
// generic.type(): (Object)Object
~~~

**Receiver được gắn sẵn** không có nghĩa đối tượng bất biến: nếu `greeter` có trạng thái mutable, lần gọi sau vẫn nhìn thấy trạng thái hiện tại của nó. “Handle không đổi” chỉ nói về liên kết thao tác/chữ ký của handle, không cam kết kết quả luôn giống nhau.

Đối với ứng dụng lặp đi lặp lại một phép gọi động, thường hợp lý để **cache handle phù hợp** thay vì tìm bằng `Lookup` ở mọi lượt. Dù vậy không tự mặc định MethodHandle luôn nhanh hơn Reflection: đặc tính hiệu năng có thể thay đổi theo độ ổn định của call site, loại adapter, cách dùng `invokeWithArguments`, JIT warmup và phiên bản JVM. Hãy benchmark đúng luồng nghiệp vụ khi tối ưu.

## 12. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| `WrongMethodTypeException` khi gọi `invokeExact` | Kiểu tham số **hoặc kiểu kết quả** tại call site không khớp `type()` | Kiểm tra toàn bộ `handle.type()`, cast rõ return type, dùng `invoke`/`asType` nếu muốn adaptation |
| `ClassCastException` khi dùng `invoke` | Adapter phải cast giá trị từ `Object` sang kiểu tham chiếu đích, nhưng giá trị không phù hợp | Kiểm tra input thực trước khi gọi |
| `NoSuchMethodException` khi `findVirtual` | Sai tên, tham số hoặc return type trong `MethodType` | Đối chiếu chính xác chữ ký khai báo sau erasure |
| `IllegalAccessException` từ `Lookup` | Lookup thiếu quyền đối với thành viên hoặc ranh giới module | Chọn lookup đúng caller/module, công khai API hoặc thiết kế quyền truy cập thích hợp |
| Gọi handle instance với thiếu tham số | Quên receiver ở vị trí đầu | Kiểm tra `handle.type().parameterCount()`; truyền receiver hoặc dùng `bindTo` |
| Handle constructor dùng `methodType(C.class,...)` để lookup | Lookup constructor cần `void.class` | Sử dụng `methodType(void.class, ...)` trong `findConstructor` |
| Phương thức ném lỗi nhưng không có `InvocationTargetException` | MethodHandle chuyển tiếp ngoại lệ gốc | Bắt loại ngoại lệ do target thực sự ném |
| `Method.invoke` lại có `InvocationTargetException` | Reflection bọc ngoại lệ của target | Dùng `getCause()` hoặc `getTargetException()` |
| Chỉ cast `Object` của Reflection vào primitive | `Method.invoke` boxing kết quả primitive | Cast/unbox wrapper phù hợp hoặc gọi handle có return type primitive |
| `handle.type()` không có generic argument | `MethodType` dùng runtime class/primitive sau erasure | Đọc metadata generic từ `Method`/`Type` nếu cần |
| Kết quả benchmark bất ngờ | JIT chưa warmup, handle thường xuyên thay đổi, adapter dư thừa | Benchmark thực tế, cache handle ổn định, đo cả chi phí lookup |

### Khi nào dùng API nào?

- Dùng `Method` khi trọng tâm là **khảo sát khai báo**, liệt kê method, đọc annotation/generic signature, tìm tên/modifier, hoặc ứng dụng Reflection truyền thống.
- Dùng `MethodHandle` khi trọng tâm là **gọi động với chữ ký kiểu được mô tả rõ**, muốn giữ/cấu hình khả năng gọi, dùng receiver binding, adapter/combinator và có khả năng tối ưu luồng gọi thường xuyên.
- Có thể **kết hợp**: tìm `Method` để đọc metadata, rồi dùng `Lookup.unreflect(method)` để chuyển sang handle khi quyền truy cập cho phép.
- Dùng cú pháp gọi trực tiếp thông thường khi kiểu và luồng gọi đã cố định ngay trong mã nguồn, vì không cần thêm cơ chế dynamic invocation.

## 13. Câu hỏi tự kiểm tra

1. **Handle khác Method ở ý nghĩa cốt lõi nào?**  
   `Method` mô tả một method khai báo; `MethodHandle` là khả năng **thực thi** một thao tác có `MethodType`, có thể qua adapter/combinator.

2. **Vì sao `lookup.findVirtual(Greeter.class, "greet", methodType(String.class, String.class))` có `parameterCount() == 2`?**  
   Method khai báo một `String`, còn handle instance chưa bound cần thêm receiver `Greeter` ở đầu.

3. **Handle `(String)String`, gọi `Object v = handle.invokeExact("x")` có hợp lệ khi chạy?**  
   Không. Return type call site là `Object`, không khớp `String`; sẽ có `WrongMethodTypeException`.

4. **Khi nào `invoke` dùng được còn `invokeExact` thất bại?**  
   Khi call site khác handle type nhưng có thể chuyển đổi theo `asType`, chẳng hạn `(Object)Object` sang handle `(String)String` với đối số thật là `String`.

5. **`bindTo` có làm thay đổi handle cũ?**  
   Không. Nó trả handle mới đã gắn tham số tham chiếu đầu tiên; handle cũ và type cũ vẫn còn.

6. **`Method.invoke` và `MethodHandle.invokeExact` xử lý lỗi target thế nào?**  
   Reflection bọc lỗi target trong `InvocationTargetException`; handle chuyển ngoại lệ target trực tiếp.

7. **Có thể dùng `MethodHandle.type()` đọc `List<String>` chi tiết không?**  
   Không. `MethodType` mô tả kiểu JVM sau erasure, không giữ generic signature đó; cần Reflection `Method.getGenericReturnType()` khi thích hợp.

8. **`MethodHandles.publicLookup()` có truy cập được private method không?**  
   Không. Quyền lookup phụ thuộc caller và các quy tắc access/module; private lookup phải đáp ứng điều kiện truy cập.

9. **Dùng MethodHandle chắc chắn nhanh hơn Method.invoke chứ?**  
   Không có bảo đảm chung. Cần xét call site, adapter, mức độ cache, JIT và đo đạc trong ngữ cảnh.

## 14. Ghi nhớ trọng tâm

- `MethodHandle` đại diện cho **một thao tác có thể thực thi** với chữ ký `MethodType`, chứ không đơn thuần là đối tượng metadata của method.
- `MethodHandles.Lookup` chọn và kiểm tra quyền khi tạo handle; `findVirtual` tạo handle có **receiver** là tham số đầu, còn `findStatic` thì không.
- `invokeExact` yêu cầu **tham số và kết quả khớp hoàn toàn** với `handle.type()`. `invoke` hỗ trợ một số phép thích nghi qua `asType`.
- `bindTo`/`asType` trả handle mới; chúng không sửa handle cũ.
- `Method.invoke` nhận `Object...` và bọc ngoại lệ do target ném; `MethodHandle` dùng call site có kiểu và truyền ngoại lệ target trực tiếp.
- `Method` có metadata annotation/generic declaration; `MethodHandle` phục vụ dynamic invocation, được mô tả bằng các runtime class/primitive sau erasure.
- Đừng mặc định hiệu năng, quyền truy cập hay chuyển đổi kiểu là giống nhau: hãy kiểm tra `type()`, chọn đúng lookup và thử nghiệm trong môi trường sử dụng.

Nắm được sự phân biệt này giúp đọc đúng các API `java.lang.invoke`, tránh sai chữ ký lúc chạy và biết khi nào dùng Reflection metadata so với khả năng gọi đã được liên kết.
