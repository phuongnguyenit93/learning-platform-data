# MethodHandle — Tham chiếu có kiểu tới hành vi có thể gọi

## 1. MethodHandle là gì?

Trong Java hiện đại, `java.lang.invoke.MethodHandle` là **một tham chiếu có kiểu và có thể thực thi** tới một hành vi, chẳng hạn phương thức, constructor, thao tác đọc/ghi trường hoặc một chuỗi thao tác đã được biến đổi và kết hợp. Nó cho phép chương trình **lựa chọn hành vi ở runtime** nhưng vẫn biểu diễn chính xác kiểu tham số và kiểu kết quả.

Ví dụ: thay vì gọi trực tiếp `Math.max(3, 7)`, chương trình có thể lấy một handle đại diện cho `Math.max(int, int)` rồi gọi handle ấy. Điểm cốt lõi là handle có kiểu `(int, int)int` — nhận hai `int`, trả về `int` — và JVM kiểm tra hợp đồng này khi gọi.

`MethodHandle` thuộc package `java.lang.invoke`, có từ Java 7 và **vẫn là API hiện hành** trên Java 17+. Nó được dùng trong hạ tầng ngôn ngữ động, `invokedynamic`, bootstrap và một số cơ chế kết nối/hành vi động. Trong code ứng dụng thông thường, hãy ưu tiên lời gọi trực tiếp, method reference hoặc lambda nếu hành vi đã được biết khi biên dịch; chọn `MethodHandle` khi **cần xây dựng, tra cứu hoặc biến đổi lời gọi ở runtime**.

### So sánh nhanh

| Cơ chế | Khi nào phù hợp? | Đặc điểm quan trọng |
| --- | --- | --- |
| Gọi trực tiếp `object.run(x)` | Đã biết class/phương thức tại compile time | Dễ đọc, được compiler kiểm tra bình thường |
| Method reference `Type::method` hoặc lambda | Cần truyền hành vi dưới dạng functional interface | Kiểu do functional interface quyết định |
| `java.lang.reflect.Method` | Cần inspect annotation, modifier, tên hoặc thành viên động | Là đối tượng reflection; `invoke` làm việc qua `Object`/mảng đối số |
| **`MethodHandle`** | Cần một lời gọi có `MethodType` cụ thể và có thể biến đổi/kết hợp | Kiểu hàm được mô tả ở runtime; `invokeExact` cần khớp chính xác |

`MethodHandle` **không phải chính phương thức Java** và không tự lưu “tên phương thức” như một phần của kiểu. Hai handle cùng kiểu có thể trỏ tới hai hành vi khác nhau. Việc tạo một handle cũng **không gọi** hành vi đó.

## 2. Kiểu hàm: MethodType

Mỗi handle có chữ ký bất biến (`MethodType`) truy cập qua `handle.type()`. Nó gồm **danh sách kiểu tham số theo thứ tự** và **kiểu trả về**:

~~~text
(int, int)int       nhận 2 int, trả int
(String, int)String nhận String + int, trả String
()String            không có tham số, trả String
(Object)void        nhận Object, không trả giá trị
~~~

Tạo kiểu hàm bằng `MethodType.methodType(returnType, parameterTypes...)`:

~~~java
import java.lang.invoke.MethodType;

MethodType sumType = MethodType.methodType(
        int.class, int.class, int.class);
System.out.println(sumType);  // (int,int)int

MethodType noArgs = MethodType.methodType(String.class);
System.out.println(noArgs);   // ()String
~~~

Đây là **đoạn độc lập về mặt API** (cần đặt trong một method để biên dịch). `MethodType` dùng `Class<?>` để mô tả các kiểu chính xác, bao gồm primitive, reference và `void.class` cho kiểu trả về. Kiểu của handle có thể khác chữ ký Java khai báo gốc, do **instance receiver** và các bộ biến đổi.

Ví dụ:

- Method static `static int add(int a, int b)` tạo handle loại `(int,int)int`.
- Method instance `String.substring(int beginIndex)` tạo handle qua `findVirtual` với loại **`(String,int)String`**: đối tượng nhận lời gọi (`this`) là tham số đầu tiên của handle.
- Constructor `Person(String name)` được tra cứu bằng kiểu constructor `(String)void` nhưng handle nhận về có loại **`(String)Person`**, vì hành vi gọi handle là *tạo đối tượng*.

**Lưu ý quan trọng:** kiểu truyền cho `Lookup.findVirtual` **không chứa receiver**; `Lookup` tự thêm receiver vào kiểu của handle kết quả. Ngược lại, kiểu của `handle.type()` có chứa receiver cho instance method chưa được bind.

## 3. Tạo MethodHandle bằng MethodHandles.Lookup

`MethodHandles.Lookup` là bộ tra cứu hành vi có kiểm soát quyền truy cập. Nó tạo các handle cho thành viên mà code đang tra cứu được phép truy cập.

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

MethodHandles.Lookup lookup = MethodHandles.lookup();

// Ví dụ trong một method có throws ReflectiveOperationException:
MethodHandle max = lookup.findStatic(
        Math.class,
        "max",
        MethodType.methodType(int.class, int.class, int.class));
~~~

Các cách tạo thường gặp:

| Cách tạo | Đối tượng được tra cứu | Kiểu handle điển hình |
| --- | --- | --- |
| `lookup.findStatic(C.class, "m", type)` | Phương thức `static` | Các tham số thực của method → kết quả |
| `lookup.findVirtual(C.class, "m", type)` | Phương thức instance gọi theo dispatch thông thường | `(C, params...)return`; có thêm receiver |
| `lookup.findConstructor(C.class, constructorType)` | Constructor; kiểu tra cứu phải trả `void` | `(params...)C` |
| `lookup.findGetter(C.class, "f", F.class)` | Đọc field instance | `(C)F` |
| `lookup.findSetter(C.class, "f", F.class)` | Ghi field instance | `(C,F)void` |
| `lookup.findStaticGetter/findStaticSetter` | Trường `static` | Không có receiver |
| `lookup.unreflect(method)` | Chuyển một `java.lang.reflect.Method` phù hợp thành handle | Phụ thuộc loại method, quyền truy cập |
| `MethodHandles.constant(type, value)` | Hành vi trả về hằng số | `()type` |
| `MethodHandles.identity(type)` | Hành vi trả lại đúng đối số | `(type)type` |

Các hàm `find...` có thể ném `NoSuchMethodException`, `NoSuchFieldException` hoặc `IllegalAccessException` khi thành viên/kiểu không khớp hoặc không được phép truy cập. `MethodHandle` có thể được tạo bởi các factory/combinator mà **không cần** trỏ tới một method nguồn riêng lẻ.

### Quyền truy cập gắn với Lookup

- `MethodHandles.lookup()` nhận quyền tra cứu dựa trên **class gọi**. Code cùng class có thể tìm private member của chính nó.
- `MethodHandles.publicLookup()` chỉ dùng khả năng truy cập công khai phù hợp; không giả định nó có thể thấy private method hoặc class không public.
- `MethodHandles.privateLookupIn(targetClass, lookup)` chỉ dùng được khi caller có quyền phù hợp và **module/package cho phép deep reflection** theo JPMS, ví dụ thông qua `opens`. Nó **không phải cách lách quyền**.
- Kiểm tra truy cập đến thành viên đích thường diễn ra lúc **tạo handle**, không phải mỗi lần gọi handle. Vì vậy, handle trỏ tới private member là một **capability nhạy cảm**: không chuyển tùy tiện cho code không đáng tin.

Không tạo `Lookup` có quyền private rồi lưu vào đối tượng công khai hoặc cấp cho plugin bên ngoài nếu không muốn trao quyền tra cứu private member tương ứng.

## 4. Gọi handle: invokeExact, invoke và invokeWithArguments

### invokeExact — kiểu ở call site phải khớp chính xác

~~~java
MethodHandle max = MethodHandles.lookup().findStatic(
        Math.class, "max",
        MethodType.methodType(int.class, int.class, int.class));

int result = (int) max.invokeExact(3, 7);
System.out.println(result); // 7
~~~

Đây là đoạn đặt bên trong method `throws Throwable`. Kiểu của handle là `(int,int)int`; kiểu mà compiler tạo cho **vị trí gọi** cũng phải là `(int,int)int`. Kiểu trả về phụ thuộc **ngữ cảnh compile time**; phép ép kiểu `(int)` là một phần quan trọng để tạo call site chính xác.

Ví dụ sau **bị lỗi** dù hai tham số đều đúng:

~~~java
// SAI về kiểu trả về call site:
Object value = max.invokeExact(3, 7);
// JVM thấy call site (int,int)Object, handle lại có (int,int)int.
// Kết quả: WrongMethodTypeException tại runtime.
~~~

`invokeExact` được khai báo theo cú pháp đặc biệt (`signature-polymorphic`): trình biên dịch không kiểm tra chữ ký đích cụ thể ở compile time vì handle là một giá trị runtime. **JVM kiểm tra chính xác** khi thực thi.

### invoke — cho phép chuyển đổi tương thích

~~~java
Object value = max.invoke((byte) 3, 7);
System.out.println(value); // 7 (đã boxing thành Integer)
~~~

`invoke` có thể chuyển đối số/kết quả theo các quy tắc tương thích với `asType`: ví dụ widening từ `byte` sang `int`, boxing/unboxing hoặc ép kiểu tham chiếu phù hợp. Nó **không** tự chuyển một chuỗi `"42"` thành số `42` hoặc tự gọi bất kỳ conversion method nào bạn muốn.

### invokeWithArguments — lời gọi động qua Object

~~~java
Object result = max.invokeWithArguments(3, 7);
System.out.println(result); // 7
~~~

Phương thức này tiện khi đầu vào đã nằm trong `List<?>` hoặc mảng `Object[]` và số lượng/tham số được quyết định ở runtime. Nó sử dụng chuyển đổi động qua `Object`, thường có chi phí cao hơn và làm lộ lỗi kiểu muộn hơn so với call site đã biết rõ. Không dùng nó để thay thế hàng loạt lời gọi thông thường.

| Cách gọi | Yêu cầu | Sai kiểu thường thấy |
| --- | --- | --- |
| `invokeExact` | Khớp chính xác từng kiểu tham số **và** kiểu trả về tại call site | `WrongMethodTypeException` |
| `invoke` | JVM có thể điều chỉnh thông qua quy tắc `asType` | `WrongMethodTypeException` hoặc lỗi cast/unboxing thích hợp |
| `invokeWithArguments` | Đối số động qua `Object`/`List`, tự thích nghi | Lỗi kiểu/arity tại runtime; thường kém hiệu quả hơn |

Cả ba dạng có thể làm hành vi đích ném exception. `invokeExact`/`invoke` khai báo `throws Throwable`; trong API ứng dụng thực tế hãy xử lý hoặc diễn đạt rõ lỗi đích, **không nuốt** `Throwable` một cách tùy tiện.

## 5. Biến đổi handle mà không đổi method gốc

Một ưu điểm cốt lõi của `MethodHandle` là tạo **adapter mới** từ handle có sẵn. Các handle là **bất biến**: adapter không sửa target.

### Bind receiver với bindTo

Từ `String.toUpperCase()` tạo handle loại `(String)String`:

~~~java
MethodHandles.Lookup lookup = MethodHandles.lookup();
MethodHandle upper = lookup.findVirtual(
        String.class, "toUpperCase", MethodType.methodType(String.class));

// Từ (String)String thành ()String:
MethodHandle fixedReceiver = upper.bindTo("java");
String text = (String) fixedReceiver.invokeExact();
System.out.println(text); // JAVA
~~~

`bindTo` cố định **tham số tham chiếu đầu tiên** và bỏ tham số ấy khỏi kiểu của handle mới. Với instance method, tham số này thường là receiver. `bindTo` **không** có nghĩa gọi target ngay lúc bind, và không dùng trực tiếp để bind tham số primitive ở đầu; khi muốn cố định nhiều/primitive argument, dùng `insertArguments`.

### insertArguments

~~~java
// add có kiểu (int,int)int:
MethodHandle addTen = MethodHandles.insertArguments(add, 0, 10);
int fifteen = (int) addTen.invokeExact(5);
System.out.println(fifteen); // 15
~~~

Đoạn trên giả định đã có handle `add` cho `static int add(int,int)`. `insertArguments(add, 0, 10)` chèn hằng số `10` vào đối số thứ nhất, biến kiểu `(int,int)int` thành `(int)int`.

### asType — đổi chữ ký tương thích

~~~java
MethodHandle valueOf = lookup.findStatic(
        String.class, "valueOf", MethodType.methodType(
                String.class, int.class));

// Gốc: (int)String. Mới: (Integer)Object.
MethodHandle adapted = valueOf.asType(
        MethodType.methodType(Object.class, Integer.class));

Object text = (Object) adapted.invokeExact(Integer.valueOf(9));
System.out.println(text); // 9
~~~

`asType` tạo một adapter có `MethodType` mới và tự xử lý **các phép chuyển kiểu được hỗ trợ**, ví dụ `Integer → int` rồi `String → Object`. Không phải mọi cặp kiểu đều tương thích: adapter có thể bị từ chối ngay lúc tạo hoặc gây `ClassCastException`/`NullPointerException` lúc chạy khi giá trị cụ thể không hợp lệ.

### Ghép hành vi với combinator

`MethodHandles` còn cung cấp:

- `filterReturnValue(target, filter)`: dùng kết quả `target` làm đầu vào cho `filter`.
- `filterArguments(target, pos, filters...)`: biến đổi đối số trước khi gọi target.
- `permuteArguments(target, newType, order...)`: thay đổi/hoán vị đối số theo cấu hình.
- `dropArguments(target, pos, types...)`: thêm đối số bị bỏ qua.
- `asCollector`/`asSpreader`: đổi giữa đối số riêng và mảng cho các trường hợp tương thích.

Ví dụ một handle `add(int,int)` cho ra `int` và một handle `String.valueOf(int)` cho ra `String` có thể ghép để nhận `(int,int)String` mà không cần viết thêm method wrapper:

~~~java
MethodHandle stringifyResult =
        MethodHandles.filterReturnValue(add, valueOf);
String answer = (String) stringifyResult.invokeExact(2, 3);
System.out.println(answer); // 5
~~~

Đây là **các fragment minh họa** dùng biến `add`, `lookup` và `valueOf` đã tạo trước đó; chương trình đầy đủ bên dưới đặt chúng trong đúng scope.

## 6. Chương trình Java 17+ chạy độc lập

Ví dụ sau kết hợp method static, instance, constructor, field getter, binding, adapter và kiểm tra lỗi kiểu. Không cần thư viện ngoài JDK.

Tạo một file **`MethodHandleDemo.java`**:

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;

public class MethodHandleDemo {
    public static int add(int a, int b) {
        return a + b;
    }

    public record Person(String name) {}

    public static final class Box {
        public int count = 9;
    }

    private static String secret() {
        return "noi-bo";
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        // 1. Static: (int,int)int.
        MethodHandle add = lookup.findStatic(
                MethodHandleDemo.class, "add",
                MethodType.methodType(int.class, int.class, int.class));
        System.out.println("type: " + add.type());
        System.out.println("add: " + (int) add.invokeExact(2, 3));

        // 2. Khóa một đối số: (int)int.
        MethodHandle addTen =
                MethodHandles.insertArguments(add, 0, 10);
        System.out.println("addTen: " + (int) addTen.invokeExact(5));

        // 3. Instance method: (String,int)String.
        MethodHandle substring = lookup.findVirtual(
                String.class, "substring",
                MethodType.methodType(String.class, int.class));
        System.out.println("substring: " +
                (String) substring.invokeExact("method-handle", 7));

        // 4. Cố định receiver: ()String.
        MethodHandle upper = lookup.findVirtual(
                String.class, "toUpperCase",
                MethodType.methodType(String.class));
        MethodHandle boundUpper = upper.bindTo("java");
        System.out.println("bound: " +
                (String) boundUpper.invokeExact());

        // 5. Constructor: tìm bằng (String)void; handle là (String)Person.
        MethodHandle construct = lookup.findConstructor(
                Person.class, MethodType.methodType(
                        void.class, String.class));
        Person person = (Person) construct.invokeExact("Lan");
        System.out.println("construct: " + person.name());

        // 6. Đọc field: (Box)int.
        MethodHandle getter =
                lookup.findGetter(Box.class, "count", int.class);
        Box box = new Box();
        System.out.println("getter: " + (int) getter.invokeExact(box));

        // 7. Combinator: (int,int)String.
        MethodHandle stringify = lookup.findStatic(
                String.class, "valueOf",
                MethodType.methodType(String.class, int.class));
        MethodHandle composed =
                MethodHandles.filterReturnValue(add, stringify);
        System.out.println("composed: " +
                (String) composed.invokeExact(2, 3));

        // 8. invoke có chuyển đổi kiểu hợp lệ.
        Object flexible = stringify.invoke((byte) 7);
        System.out.println("invoke: " + flexible);

        // 9. asType tạo adapter riêng: (Integer)Object.
        MethodHandle adapted = stringify.asType(
                MethodType.methodType(Object.class, Integer.class));
        Object adaptedResult =
                (Object) adapted.invokeExact(Integer.valueOf(9));
        System.out.println("asType: " + adaptedResult);

        // 10. invokeExact không tự đổi int -> Object ở call site.
        try {
            Object unexpected = add.invokeExact(2, 3);
            System.out.println(unexpected);
        } catch (WrongMethodTypeException ex) {
            System.out.println("wrong type: " +
                    ex.getClass().getSimpleName());
        }

        // 11. Lookup trong chính class được phép lấy private method.
        MethodHandle privateHandle = lookup.findStatic(
                MethodHandleDemo.class, "secret",
                MethodType.methodType(String.class));
        System.out.println("private: " +
                (String) privateHandle.invokeExact());
    }
}
~~~

Biên dịch và chạy tại thư mục chứa file (JDK 17+):

~~~bash
javac MethodHandleDemo.java
java MethodHandleDemo
~~~

Hoặc với chế độ chạy một source file của JDK:

~~~bash
java MethodHandleDemo.java
~~~

`stdout` dự kiến:

~~~text
type: (int,int)int
add: 5
addTen: 15
substring: handle
bound: JAVA
construct: Lan
getter: 9
composed: 5
invoke: 7
asType: 9
wrong type: WrongMethodTypeException
private: noi-bo
~~~

Những điểm cần quan sát:

1. `add.type()` xác nhận handle là `(int,int)int` dù được tìm bằng tên ở runtime.
2. `insertArguments` biến lời gọi hai đối số thành một đối số.
3. `findVirtual` tự thêm receiver `String` vào kiểu handle; `bindTo` lại cố định receiver.
4. `findConstructor` trả về đối tượng `Person`, dù kiểu constructor dùng khi tìm có return `void`.
5. `findGetter` đọc trạng thái của đúng đối tượng `Box`.
6. `filterReturnValue` xây chuỗi hành vi: cộng hai số, rồi chuyển `int` thành `String`.
7. `invoke` chuyển `byte` thành `int` và giá trị `String` thành `Object` theo kiểu call site.
8. `invokeExact` thất bại khi biến kiểu trả về mong muốn thành `Object` dù đối số đúng; việc `catch` là chủ ý trong ví dụ để nhìn rõ lỗi.
9. Method handle tới `private` method được tạo **ngay trong class có quyền truy cập**; không suy ra class bên ngoài cũng tạo được.

Đây là ví dụ học tập dùng `throws Throwable` để trình bày ngắn gọn các lời gọi signature-polymorphic. Trong hệ thống thực tế, hãy đặt ranh giới xử lý exception có ý nghĩa nghiệp vụ và không công khai một private handle cho thành phần không tin cậy.

## 7. Sai kiểu và sai quyền: phân biệt nguyên nhân

| Lỗi hoặc hiện tượng | Khi nào xảy ra? | Cách khắc phục |
| --- | --- | --- |
| `NoSuchMethodException` khi `findStatic/findVirtual` | Sai tên, sai số/kiểu tham số, kiểu trả về, hoặc dùng nhầm static/instance | Đối chiếu chữ ký method và `MethodType`; `findVirtual` bỏ receiver ở kiểu tra cứu |
| `NoSuchFieldException` | Sai tên/kiểu field | Kiểm tra field và loại primitive/reference chính xác |
| `IllegalAccessException` lúc tìm handle | `Lookup` không đủ quyền; ràng buộc class/module | Tra cứu qua `Lookup` được cấp quyền hợp lệ, thiết kế `exports/opens` nếu thật sự cần |
| `WrongMethodTypeException` lúc gọi | Call-site type/arity không tương thích với handle | In `handle.type()`; xem cả **kiểu trả về** và receiver |
| `ClassCastException` hoặc `NullPointerException` | Adapter/cast/unboxing hợp lệ ở cấp kiểu nhưng giá trị runtime không tương thích hoặc `null` không unbox được | Kiểm tra giá trị, kiểu thực tế, nullable và hợp đồng `asType` |
| Nhầm `findVirtual` với `findStatic` | Quên receiver ở đầu handle cho instance method | Gọi với đúng receiver hoặc `bindTo(receiver)` |
| Cố gán `MethodHandle` trực tiếp cho functional interface | Hai abstraction khác nhau | Dùng lambda/wrapper, hoặc `LambdaMetafactory` khi xây hạ tầng động chuyên biệt |
| Dùng `invokeWithArguments` trong vòng lặp nóng | Boxing/array/chuyển kiểu động không cần thiết | Cân nhắc `invokeExact`/adapter có kiểu, benchmark trước khi tối ưu |
| Tưởng handle tự theo dõi method mới sau khi class thay đổi | Handle gắn với hành vi đã được resolve | Xác định rõ lifecycle của class loader, bootstrap, cache và phương án tạo lại |

Không chuyển handle private hoặc `Lookup` nhiều quyền cho bên thứ ba chỉ vì phương thức chạy được: quyền truy cập đã được kiểm tra lúc tạo nên việc chia sẻ handle chính là chia sẻ khả năng gọi hành vi đó.

## 8. Khi nào MethodHandle hữu ích trong ứng dụng Java hiện đại?

Các tình huống phù hợp:

- **Framework/hạ tầng động:** lựa chọn accessor hoặc logic xử lý theo metadata đã kiểm tra, rồi cache một handle có kiểu thay vì tra cứu lại mỗi lần.
- **Bộ chuyển đổi và adapter:** ghép xử lý có cấu trúc qua `filterArguments`, `filterReturnValue`, `insertArguments`, `asType`.
- **Tích hợp runtime ngôn ngữ:** một số cơ chế bootstrap và `invokedynamic` có call site gắn tới method handle.
- **Interop có kiểm soát:** chuyển method hợp lệ từ Core Reflection qua `unreflect` khi cần dùng mô hình lời gọi có kiểu.

Các giới hạn cần ghi nhớ:

1. **Không có bảo đảm luôn nhanh hơn reflection hay lời gọi trực tiếp.** Chi phí lookup, adapter, boxing, độ ổn định call site, cách JVM JIT tối ưu và việc cache quyết định hiệu năng. Đo bằng benchmark phù hợp trước khi kết luận.
2. **Không lạm dụng cho lời gọi bình thường.** Lambda hoặc method reference thường rõ ràng và dễ bảo trì hơn khi chữ ký đã biết.
3. **Không dùng MethodHandle để phá tính đóng gói.** Quy tắc `Lookup` và module system vẫn áp dụng.
4. **Không nhầm với VarHandle.** Khi cần thao tác kiểu truy cập bộ nhớ `volatile`, `compareAndSet` hoặc các phép atomic trên field/array, API chuyên dụng là `java.lang.invoke.VarHandle`. Method handle có thể trỏ tới thao tác field nhưng không tự biến thao tác đó thành nguyên tử.
5. **Không đoán kiểu từ tên.** Luôn đọc `handle.type()` và thiết kế call site, adapter, conversion dựa trên chữ ký thực.

### Checklist ngắn trước khi dùng handle

1. Hành vi đích là static, instance, constructor hay field?
2. `MethodType` tra cứu có đúng kiểu tham số và kiểu trả về không? Với instance, đã tính receiver vào **kiểu handle sau tra cứu** chưa?
3. `Lookup` của caller có quyền hợp lệ đối với class/member/module không?
4. Dự định gọi `invokeExact`, `invoke` hay `invokeWithArguments`? Call site có khớp cả kiểu trả về không?
5. Nếu biến đổi `asType`/`bindTo`/`insertArguments`, đã kiểm tra kiểu handle **mới** chưa?
6. Handle được cache/chia sẻ ở đâu, ai có thể gọi nó, và dữ liệu hay private capability có bị rò rỉ không?
7. Lợi ích của dispatch động có đáng độ phức tạp bổ sung so với lời gọi Java thông thường không?

**Ghi nhớ:** `MethodHandle` = **hành vi có thể gọi + `MethodType` rõ ràng + quyền tạo handle được kiểm tra bằng `Lookup`**. Nó cho phép xây dựng và biến đổi lời gọi động, nhưng lúc thực thi vẫn cần tôn trọng chữ ký chính xác và các quy tắc chuyển kiểu.

## Tài liệu tham khảo Java hiện hành

- [Java SE 17 — MethodHandle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html): kiểu handle, `invokeExact`, `invoke`, `invokeWithArguments`, `bindTo` và `asType`.
- [Java SE 17 — MethodHandles](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html): `lookup`, combinator, factory.
- [Java SE 17 — MethodHandles.Lookup](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): tạo handle cho static/virtual/constructor/field và kiểm tra quyền.
- [Java SE 17 — MethodType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html): mô tả chữ ký hàm.
