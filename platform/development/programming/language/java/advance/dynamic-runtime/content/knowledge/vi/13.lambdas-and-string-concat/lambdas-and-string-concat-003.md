# 13.3 Phân biệt `factoryType`, `interfaceMethodType`, `implementation` và `dynamicMethodType`

Trong Java 8 trở lên, compiler thường dùng lệnh bytecode `invokedynamic` kết hợp `java.lang.invoke.LambdaMetafactory.metafactory` để triển khai lambda expression và method reference. Khi xem `javap -v`, bạn sẽ thấy một số `MethodType` cùng một `MethodHandle` mô tả **những việc hoàn toàn khác nhau**:

- **`factoryType`** mô tả cách **tạo ra function object**, tức kiểu của chính `invokedynamic` call site.
- **`interfaceMethodType`** mô tả **chữ ký JVM của phương thức SAM** mà function object phải hiện thực, thường là chữ ký đã *erasure*.
- **`implementation`** là **direct MethodHandle** trỏ tới method/constructor thực sự thực thi hành vi, có thể chứa thêm tham số được capture và receiver.
- **`dynamicMethodType`** mô tả chữ ký **đã chuyên biệt hóa** (*instantiated method type*) dùng để kiểm tra tham số/kết quả tại lúc gọi SAM, ví dụ `(String)String` thay cho SAM erased `(Object)Object`.

Bốn thông tin này không đồng nghĩa nhau, dù đôi khi một vài chữ ký tình cờ giống nhau. Sai khác giữa chúng quyết định cả việc liên kết lambda có thành công hay không, thời điểm capture biến, cách gọi body, kiểm tra kiểu runtime và nguyên nhân của `LambdaConversionException` hay `ClassCastException`.

Bài này lấy Java 17 làm chuẩn; mã chạy được với `javac --release 17` và JDK 17+. Mọi ví dụ dùng API `java.lang.invoke` chính thức, không cần ASM hoặc mã nguồn JDK nội bộ.

## 1. Hợp đồng của `LambdaMetafactory.metafactory`

Đây là chữ ký thật của phương thức bootstrap:

~~~java
public static CallSite metafactory(
    MethodHandles.Lookup caller,
    String interfaceMethodName,
    MethodType factoryType,
    MethodType interfaceMethodType,
    MethodHandle implementation,
    MethodType dynamicMethodType
) throws LambdaConversionException
~~~

Đoạn trên là **chữ ký API để đọc**, không phải khai báo cho người học dán vào một class. Phần còn lại tập trung vào bốn tham số sau `caller` và `interfaceMethodName`.

| Thành phần | Nó mô tả gì? | Ví dụ khi tạo `Function<String,String>` từ `String upper(String)` |
| --- | --- | --- |
| `factoryType` | Kiểu của **factory call site** tạo function object; các tham số là **giá trị được capture**, return type là functional interface | `()Function` nếu không capture |
| `interfaceMethodType` | Chữ ký SAM **được function object hiện thực ở mức JVM**, gồm tên từ `interfaceMethodName`; có thể đã xóa generic | `(Object)Object` vì `Function.apply(T)` erases thành `apply(Object):Object` |
| `implementation` | Direct method handle đến phương thức/constructor body; kiểu đầy đủ gồm receiver nếu method instance và các tham số captured nếu có | `(String)String` trỏ `upper(String)` |
| `dynamicMethodType` | Chữ ký SAM **đã instantiate/chuyên biệt hóa** để runtime kiểm tra trước/sau khi gọi implementation | `(String)String` |

Ở ví dụ không capture phía trên, `implementation.type()` và `dynamicMethodType` cùng là `(String)String`; **đó chỉ là trùng hợp về chữ ký**, không phải hai vai trò giống nhau. Chỉ cần capture một biến, implementation có thêm tham số trong khi dynamic method vẫn chỉ mô tả những đối số của `apply`.

### Hai tham số ngầm định còn lại

- `caller` là một `MethodHandles.Lookup` có quyền của **class chứa invokedynamic instruction**. Theo API `metafactory`, nó cần lookup có **full privilege access**. Khi JVM gọi BSM cho `invokedynamic`, JVM tự cấp lookup; khi gọi trực tiếp từ Java source như ví dụ phần 5, dùng `MethodHandles.lookup()` tại class có quyền phù hợp.
- `interfaceMethodName` là **tên method** mà function object cần triển khai, chẳng hạn `"apply"` của `Function`, `"map"` của interface tự định nghĩa, hay `"applyAsInt"` của `ToIntFunction`. Tên này không bắt buộc trùng với tên method implementation.

Khi thực sự liên kết bằng bytecode `invokedynamic`, JVM truyền **ba argument chuẩn**: `caller`, `interfaceMethodName` và `factoryType`, được suy từ ngữ cảnh lệnh gọi/name-and-type. Ba phần **static bootstrap arguments** của `LambdaMetafactory.metafactory` là `interfaceMethodType`, `implementation` và `dynamicMethodType`. Chúng nằm trong metadata `BootstrapMethods` của class file, không được tính là captured runtime variables.

## 2. Ba giai đoạn: linkage, capture và invocation

`LambdaMetafactory` có ba thời điểm khác nhau, và việc đọc sai giai đoạn thường dẫn đến hiểu sai `factoryType`.

~~~text
(1) LINKAGE — JVM phân giải invokedynamic site
    caller = Lookup của class chứa site
    name = tên SAM, ví dụ "apply"
    factoryType = (String)Function
    interfaceMethodType = (Object)Object
    implementation = MH (String,String)String
    dynamicMethodType = (String)String
                     |
                     v
           LambdaMetafactory.metafactory(...)
                     |
                     v
        CallSite type = (String)Function
                     |
                     v
(2) CAPTURE — gọi CallSite target bằng prefix runtime "Hi-"
        factory("Hi-") -> Function object
                     |
                     v
(3) INVOCATION — gọi method SAM trên function object
        function.apply("Ada")
                     |
             dynamic (String)String
                     |
             implementation(prefix,text)
                     |
                     v
                   "Hi-Ada"
~~~

**Linkage**: BSM nhận kiểu/tên/handle/metadata, kiểm tra ràng buộc và trả một `CallSite`. `CallSite.type()` phải bằng `factoryType`. JVM có thể bootstrap trước lần execute đầu tiên; không được dựa cứng vào thời điểm chính xác cho side effect.

**Capture**: target handle của `CallSite` được gọi với **các giá trị runtime của biến captured**. Nó trả về một object thuộc functional interface. Capture có thể tạo object mới hoặc tái sử dụng một object phù hợp; không giả định identity/việc cấp phát nhất định.

**Invocation**: caller gọi method SAM như `f.apply(input)`. Function object chuyển các captured values (đã được lưu tại capture) và arguments của invocation tới implementation, với kiểm tra/chuyển đổi kiểu cần thiết.

Đặc biệt:

- `factoryType` chi phối **capture-time**: số/kiểu captured arguments và kiểu function object trả về.
- `interfaceMethodType` chi phối **method signature thực sự phải triển khai** trên function object.
- `dynamicMethodType` chi phối **ràng buộc kiểu được kiểm tra khi gọi SAM**.
- `implementation` chi phối **hành vi thật** của method body.

Không nhập nhằng “giá trị captured” với “static bootstrap arguments”: captured value thường là một object/primitive được lấy từ chương trình **mỗi lần factory chạy**, còn các static arguments là metadata ở **constant pool** dùng lúc linkage.

## 3. Ví dụ không capture: vì sao có `()Function` và `(Object)Object`?

Lấy method Java:

~~~java
static String upper(String text) {
    return text.toUpperCase(java.util.Locale.ROOT);
}
~~~

Và method reference:

~~~java
java.util.function.Function<String, String> f = MyClass::upper;
~~~

Hai đoạn trên chỉ là **snippet minh họa** (class `MyClass` không được định nghĩa ở đây); chương trình hoàn chỉnh nằm trong phần 6.

### Phân tích kiểu

1. `Function<T,R>.apply(T)` có chữ ký JVM sau erasure là **`(Object)Object`**. Generic type arguments `<String,String>` không làm thay đổi descriptor JVM của `Function.apply`.
2. `dynamicMethodType` chuyên biệt hóa kiểu SAM thành **`(String)String`**, vì compiler biết invocation mong argument/result `String`.
3. Implementation `MyClass.upper` là một static method trực tiếp kiểu **`(String)String`**.
4. Method reference này **không capture biến nào**. Vì vậy factory type không có input và trả functional interface object: **`()Function`**.

Bốn trường:

~~~text
factoryType          = ()Function
interfaceMethodType  = (Object)Object
implementation.type  = (String)String
dynamicMethodType    = (String)String
~~~

Khi code gọi `f.apply("java")`, JVM dùng interface call `apply(Object):Object` ở mức erasure, function object có thể thực hiện **runtime cast sang `String`** trước khi gọi implementation. Giá trị trả về thực tế là String và được sử dụng dưới kiểu generic thích hợp.

**Tại sao `interfaceMethodType` không phải `(String)String`?** Vì generic `Function.apply` thật sự có descriptor `(Object)Object` sau erasure. Nếu muốn triển khai method mang descriptor khác trên object mà lại bỏ method erased, caller `invokeinterface Function.apply(Object)Object` sẽ không tìm đúng method đã cam kết.

**Tại sao `factoryType` không phải `(String)String`?** Factory site **tạo Function object**, không trực tiếp gọi `upper`. Lời gọi `f.apply(...)` diễn ra về sau.

## 4. Ví dụ capture: `K + N = M` và thứ tự các tham số

Xét:

~~~java
static String combine(String prefix, String text) {
    return prefix + text;
}
~~~

Một hàm tạo:

~~~java
Function<String, String> withPrefix(String prefix) {
    return text -> combine(prefix, text);
}
~~~

Đây cũng chỉ là **snippet minh họa**; các chương trình hoàn chỉnh bên dưới khai báo đầy đủ kiểu và class.

Lambda trên có:

- `K=1` captured parameter: `prefix` kiểu `String`, do đó `factoryType=(String)Function`.
- `N=1` SAM invocation parameter: `text` kiểu `String` (ở dạng erased `Object`), do đó `interfaceMethodType=(Object)Object`, `dynamicMethodType=(String)String`.
- `M=2` implementation parameters: `prefix` và `text`, do đó `implementation=(String,String)String`.

Công thức liên kết cơ bản của `LambdaMetafactory` là:

\[
K+N=M
\]

Trong đó **K** là số capture arguments được factory nhận, **N** là số tham số của SAM method khi gọi function object, và **M** là số tham số trong **MethodHandle implementation**, **bao gồm receiver của instance method** khi áp dụng.

~~~text
factoryType (String)Function             K = 1
               |
               | prefix = "Hi-"
               v
          Function object
               |
               | .apply(text="Ada")       N = 1
               v
implementation (String,String)String      M = 2
                prefix,text
                "Hi-","Ada"
               |
               v
              "Hi-Ada"
~~~

Không thêm captured parameters vào `dynamicMethodType`: nó chỉ mô tả **SAM invocation**. Cũng không thêm `text` vào `factoryType`: ở capture time, input `text` chưa xuất hiện.

## 5. Chương trình hoàn chỉnh: tự gọi `LambdaMetafactory.metafactory`

Phần này **gọi API BSM trực tiếp bằng Java** để thấy chính xác bốn tham số, chứ không tự phát sinh một opcode invokedynamic. Ví dụ bytecode `invokedynamic` thật được xem ở phần 6.

Lưu **`MetaFactoryTypesDemo.java`**:

~~~java
import java.lang.invoke.*;

public class MetaFactoryTypesDemo {
    @FunctionalInterface
    public interface Mapper<T> {
        T map(T value);
    }

    public static String combine(String prefix, String text) {
        return prefix + text;
    }

    @SuppressWarnings({"rawtypes", "unchecked"})
    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        MethodType factoryType =
                MethodType.methodType(Mapper.class, String.class);
        MethodType interfaceMethodType =
                MethodType.methodType(Object.class, Object.class);

        MethodHandle implementation = lookup.findStatic(
                MetaFactoryTypesDemo.class, "combine",
                MethodType.methodType(
                        String.class, String.class, String.class));

        MethodType dynamicMethodType =
                MethodType.methodType(String.class, String.class);

        CallSite site = LambdaMetafactory.metafactory(
                lookup, "map", factoryType, interfaceMethodType,
                implementation, dynamicMethodType);

        System.out.println("factoryType=" + factoryType);
        System.out.println("interfaceMethodType=" + interfaceMethodType);
        System.out.println("implementation=" + implementation.type());
        System.out.println("dynamicMethodType=" + dynamicMethodType);
        System.out.println("callSiteType=" + site.type());

        Mapper<String> mapper = (Mapper<String>)
                site.getTarget().invokeExact("Hi-");
        System.out.println("map=" + mapper.map("Ada"));

        Mapper raw = mapper;
        try {
            Object invalid = raw.map(Integer.valueOf(42));
            System.out.println("unexpected=" + invalid);
        } catch (ClassCastException ex) {
            System.out.println("rawInput=" + ex.getClass().getSimpleName());
        }
    }
}
~~~

Biên dịch và chạy:

~~~sh
javac --release 17 MetaFactoryTypesDemo.java
java MetaFactoryTypesDemo
~~~

**Stdout chính xác:**

~~~text
factoryType=(String)Mapper
interfaceMethodType=(Object)Object
implementation=(String,String)String
dynamicMethodType=(String)String
callSiteType=(String)Mapper
map=Hi-Ada
rawInput=ClassCastException
~~~

Phân tích từng đoạn:

1. `factoryType` là `(String)Mapper` vì factory nhận một captured `prefix` và trả một `Mapper`. Nó **không** trả String; String là kết quả của lần gọi `map` về sau.
2. `interfaceMethodType` là `(Object)Object` vì `Mapper<T>.map(T)` erases thành `map(Object):Object`.
3. `implementation` là direct handle tới `combine(String,String):String`, lấy từ `lookup.findStatic`. Nó nhận **2** arguments.
4. `dynamicMethodType` là `(String)String`: tham số/trả về của SAM sau khi specialize `T=String`.
5. `LambdaMetafactory.metafactory(...)` trả `CallSite` có kiểu `(String)Mapper` đúng bằng `factoryType`.
6. `site.getTarget().invokeExact("Hi-")` thực hiện **capture**. `"Hi-"` là runtime value truyền vào factory, không phải đối số `metafactory`. Call-site return cast sang `Mapper` là cần thiết cho `invokeExact`.
7. `mapper.map("Ada")` là **invocation**. Generated function object chuyển `"Hi-"` và `"Ada"` tới implementation, trả `"Hi-Ada"`.
8. Biến `raw` cố tình bỏ kiểm tra generic của source; vì method ở mức erased nhận Object, lời gọi với `Integer(42)` đi vào được nhưng generated implementation **cast xuống String** theo `dynamicMethodType` và ném `ClassCastException`. Đây là lý do dynamic type không chỉ là thông tin trang trí.

`@SuppressWarnings` chỉ tắt cảnh báo raw/unchecked ở demo, **không làm type system mất quyền kiểm tra runtime**. Trong ứng dụng bình thường tránh raw types và unchecked conversions.

### Dạng biểu thức tương đương về ý nghĩa

~~~text
CallSite target (String)Mapper
          |
       "Hi-"         [capture, một lần khi tạo object]
          |
          v
       Mapper object
          |
     map("Ada")      [SAM invocation]
          |
          v
 combine("Hi-","Ada") [implementation, 2 tham số]
          |
          v
      "Hi-Ada"
~~~

Đây là **sơ đồ ngữ nghĩa**, không cam kết class implementation được tạo như thế nào, có hidden class hay không, hoặc có tạo mới object ở mỗi lần capture hay không.

## 6. `javap` cho lambda Java source: ba static args ở đâu?

Để thấy compiler tự sinh `invokedynamic`, tạo **`CompiledLambdaTypesDemo.java`**:

~~~java
import java.util.Locale;
import java.util.function.Function;

public class CompiledLambdaTypesDemo {
    static String upper(String text) {
        return text.toUpperCase(Locale.ROOT);
    }

    static Function<String, String> withPrefix(String prefix) {
        return text -> prefix + text;
    }

    public static void main(String[] args) {
        Function<String, String> direct =
                CompiledLambdaTypesDemo::upper;
        Function<String, String> captured = withPrefix("Hi-");

        System.out.println("direct=" + direct.apply("java"));
        System.out.println("captured=" + captured.apply("Ada"));

        String value = args.length == 0 ? "X" : args[0];
        System.out.println("concat=" + ("value=" + value));
    }
}
~~~

~~~sh
javac --release 17 CompiledLambdaTypesDemo.java
java CompiledLambdaTypesDemo
javap -v -p CompiledLambdaTypesDemo
~~~

**Stdout của lệnh `java`:**

~~~text
direct=JAVA
captured=Hi-Ada
concat=value=X
~~~

Ở bản biên dịch OpenJDK được sử dụng để kiểm tra, `javap -v` hiển thị các `InvokeDynamic` sites liên quan đến lambda với descriptor tương ứng:

~~~text
apply:()Ljava/util/function/Function;
apply:(Ljava/lang/String;)Ljava/util/function/Function;
~~~

Và trong `BootstrapMethods` của các sites, method handle bootstrap trỏ tới `java/lang/invoke/LambdaMetafactory.metafactory`, với **ba static arguments** theo thứ tự:

~~~text
1. samMethodType          (Ljava/lang/Object;)Ljava/lang/Object;
2. implMethod             REF_invokeStatic ... upper(...) hoặc lambda$withPrefix$0(...)
3. instantiatedMethodType (Ljava/lang/String;)Ljava/lang/String;
~~~

Các số `#...` của constant pool phụ thuộc cách compiler tạo class; không cần nhớ số index. Hãy nhớ **vai trò** của từng thông tin:

| Site | Descriptor của `invokedynamic` = factoryType | Erased SAM = interfaceMethodType | Direct implementation | Instantiated SAM = dynamicMethodType |
| --- | --- | --- | --- | --- |
| `CompiledLambdaTypesDemo::upper` | `()Function` | `(Object)Object` | `upper(String)String` | `(String)String` |
| `text -> prefix + text` trong `withPrefix` | `(String)Function` | `(Object)Object` | Compiler-generated `lambda$withPrefix$0(String,String)String` | `(String)String` |

**Quan trọng:** `factoryType` nằm ở **descriptor của `InvokeDynamic`**, không nằm trong ba static args của `LambdaMetafactory`. Ngược lại, ba static args là `interfaceMethodType`, direct `implementation` và `dynamicMethodType`. JVM tự cấp `caller Lookup` và `interfaceMethodName` trong lúc liên kết.

Với compiler khác hoặc flags khác, bytecode có thể mang cấu trúc tương đương nhưng phương thức sinh tự động hoặc cách concat được tối ưu khác; không suy diễn tên synthetic `lambda$...` là public API ổn định.

### Vì sao `implementation` của capturing lambda có hai tham số?

Compiler desugar body `text -> prefix + text` thành một method nhận **capture trước**, rồi SAM invocation arguments sau. Chẳng hạn:

~~~java
private static String lambda$withPrefix$0(
        String prefix, String text) {
    return prefix + text;
}
~~~

Đoạn này chỉ là **mô hình minh họa compiler-generated method**, không phải khai báo bạn cần thêm vào source đã có (nếu thêm sẽ dễ trùng tên compiler). Kiểu MH của nó là `(String,String)String`; phép capture giữ `prefix`, sau đó `apply` chuyển `text` vào phần còn lại.

**Không nhầm `prefix` với static BSM argument:** prefix là **dynamic operand** của factory site khi chạy, nên có thể khác cho từng function object; trong khi ba static BSM args là metadata dùng để cấu hình cách tạo function object.

## 7. Ràng buộc linkage: K, N, M và hướng thích nghi kiểu

JavaDoc `LambdaMetafactory` đặt tên:

- **K** = số tham số của `factoryType`, các kiểu `D1...Dk`, return `Rd` (functional interface).
- **N** = số tham số của `interfaceMethodType`, các kiểu `U1...Un`, return `Ru`.
- **M** = số tham số của `implementation.type()`, các kiểu `A1...Am`, return `Ra`. Nếu implementation là instance method, kiểu MH **đã chứa receiver đầu tiên**.
- **N** cũng là số tham số của `dynamicMethodType`, các kiểu `T1...Tn`, return `Rt`.

Những invariant cốt lõi:

1. **`K + N = M`.** Captured arguments và SAM invocation arguments phải cung cấp đủ số argument cho implementation.
2. **`Di = Ai` với i từ 1 đến K.** Kiểu của từng captured argument trong factory phải **trùng chính xác** kiểu của vị trí đầu tương ứng trong implementation handle. Không thể tùy tiện giả định widening/cast cho capture.
3. **`interfaceMethodType` và `dynamicMethodType` có cùng N.** Từng `Ti` hoặc bằng `Ui`, hoặc cả hai là reference types và `Ti` là subtype của `Ui`.
4. **`Rt` hoặc bằng `Ru`, hoặc là reference subtype của `Ru`.** Instantiated return type phải tương thích với return type erased của method SAM.
5. **`Ti` phải adaptable đến `A(K+i)`**, tức kiểu chuyên biệt hóa ở SAM invocation phải truyền được cho argument implementation sau phần capture, theo bảng adaptation quy định riêng của metafactory.
6. **Nếu `Rt` không phải `void`, `Ra` phải khác `void` và adaptable tới `Rt`.** Nếu `Rt` là `void`, implementation có thể trả kết quả rồi bỏ giá trị.
7. Return type `Rd` của `factoryType` phải là một interface phù hợp; `implementation` phải là **direct method handle** tham chiếu tới method hoặc constructor mà metafactory có thể nhận diện. `caller` cần lookup có full privilege access.

Ví dụ `MetaFactoryTypesDemo`:

~~~text
K=1: factoryType          (String)Mapper
N=1: interfaceMethodType  (Object)Object
M=2: implementation       (String,String)String
N=1: dynamicMethodType    (String)String

D1 = String
A1 = String       [capture trùng chính xác]
T1 = String
A2 = String       [SAM argument tương thích]
Ru = Object
Rt = String       [String subtype Object]
Ra = String       [implementation return tương thích]
K + N = M         [1 + 1 = 2]
~~~

**Tại sao cần chia `K` và `N`?** Một implementation có 2 tham số không có nghĩa SAM cũng có 2 tham số. Nó có thể là một tham số được capture và một tham số sẽ xuất hiện ở mỗi lần gọi SAM. Đó là lý do `factoryType` và `dynamicMethodType` phải tách riêng.

### Link-time vs invocation-time type checks

- **Link-time:** metafactory kiểm tra số lượng argument và quan hệ kiểu theo hợp đồng để xác nhận có thể tạo function object. Vi phạm có thể ném `LambdaConversionException`.
- **Capture-time:** target factory được invoke với K captured values; với bound instance method reference có captured receiver, hợp đồng yêu cầu receiver này khác null.
- **Invocation-time:** function object's SAM method thực hiện conversion cần thiết và có thể cast/check reference arguments hoặc return. Nếu caller ép đi theo raw interface và truyền kiểu sai, có thể nhận `ClassCastException`; không cần liên kết lambda lại.

**Lưu ý về bảng conversion:** quy tắc adaptation của `LambdaMetafactory` không đơn giản là gọi `implementation.asType(...)` trên toàn bộ kiểu trong mọi tình huống. Nó có điều kiện riêng: primitive widening, boxing/unboxing hợp lệ, cast/chuyển đổi reference và kiểm tra runtime; với parameter reference, khả năng thích nghi ở linkage có hạn chế subtype. Đừng dùng giả định “`asType` được gì, metafactory tự động được mọi thứ ấy” để lách invariant.

### `interfaceMethodType` và `dynamicMethodType` có thể giống nhau

Nếu SAM không có generic và các kiểu đã phù hợp, cả hai có thể cùng là `(int)boolean` hoặc `(String)String`. Nhưng mục đích vẫn khác:

- interfaceMethodType = method bytecode phải hiện thực.
- dynamicMethodType = phương thức đó được kiểm tra/chuyên biệt hóa ra sao ở invocation.

Không cố tạo hai MethodType khác nhau chỉ để chứng minh chúng khác vai trò.

## 8. Instance method: receiver có thể là capture hoặc SAM argument

`MethodHandles.Lookup.findVirtual` trả direct MH có receiver ở **tham số đầu**, dù method source không viết receiver trong dấu ngoặc.

Ví dụ `String.length()`:

~~~java
MethodHandle implementation = MethodHandles.lookup().findVirtual(
    String.class, "length", MethodType.methodType(int.class)
);
System.out.println(implementation.type()); // (String)int
~~~

Đây là **snippet minh họa** trong ngữ cảnh có import `java.lang.invoke.*`, không phải chương trình độc lập. Receiver `String` đã là **một trong M tham số** của implementation.

### Hai cách diễn giải cùng implementation `String.length`

| Method reference | `factoryType` | `interfaceMethodType` | `implementation` | `dynamicMethodType` |
| --- | --- | --- | --- | --- |
| Không bind receiver: `String::length` với `ToIntFunction<String>` | `()ToIntFunction` | `(Object)int` | `(String)int` | `(String)int` |
| Bind receiver: `"Hello"::length` với `Supplier<Integer>` | `(String)Supplier` | `()Object` | `(String)int` | `()Integer` |

**Unbound**: receiver được chuyển vào như **argument của SAM invocation**, nên `K=0,N=1,M=1`. **Bound**: receiver được **capture khi factory chạy**, nên `K=1,N=0,M=1`. Với `Supplier<Integer>`, `int` từ implementation được boxing thành `Integer`, còn SAM erased return type là `Object`.

Không gọi `String::length` là “implementation có 0 tham số” chỉ vì method Java `length()` không có tham số source. Type của *virtual MethodHandle* là `(String)int`.

### Ví dụ 2: unbound receiver, không capture

Lưu **`ReceiverTypesDemo.java`**:

~~~java
import java.lang.invoke.*;
import java.util.function.ToIntFunction;

public class ReceiverTypesDemo {
    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodHandle implementation = lookup.findVirtual(
                String.class, "length",
                MethodType.methodType(int.class));

        MethodType factoryType =
                MethodType.methodType(ToIntFunction.class);
        MethodType interfaceMethodType =
                MethodType.methodType(int.class, Object.class);
        MethodType dynamicMethodType =
                MethodType.methodType(int.class, String.class);

        CallSite site = LambdaMetafactory.metafactory(
                lookup, "applyAsInt", factoryType, interfaceMethodType,
                implementation, dynamicMethodType);

        System.out.println("factoryType=" + factoryType);
        System.out.println("interfaceMethodType=" + interfaceMethodType);
        System.out.println("implementation=" + implementation.type());
        System.out.println("dynamicMethodType=" + dynamicMethodType);

        ToIntFunction<String> length =
                (ToIntFunction<String>) site.getTarget().invokeExact();
        System.out.println("length=" + length.applyAsInt("Hello"));
    }
}
~~~

~~~sh
javac --release 17 ReceiverTypesDemo.java
java ReceiverTypesDemo
~~~

**Stdout:**

~~~text
factoryType=()ToIntFunction
interfaceMethodType=(Object)int
implementation=(String)int
dynamicMethodType=(String)int
length=5
~~~

Giải thích: `site.getTarget().invokeExact()` không nhận argument vì factory không capture; sau đó `length.applyAsInt("Hello")` truyền receiver String làm SAM argument. Generated SAM implementation nhận erased `Object`, kiểm tra/cast thành `String`, gọi `String.length()` và trả primitive `int`.

### Captured receiver có thể là null không?

Theo hợp đồng `LambdaMetafactory`, khi `implementation` tham chiếu instance method và có captured arguments (`K>0`), **captured argument đầu tiên tương ứng receiver phải khác null**. Không thiết kế code phụ thuộc vào việc một JVM cụ thể sẽ phát hiện `null` ở cùng một dòng source trên mọi implementation/tình huống. Trong mã Java bình thường, receiver null ở bound method reference là đầu vào không hợp lệ.

## 9. Bốn lỗi linkage có thể tái hiện

Một `MethodHandle` có vẻ “gọi được bằng `invoke`” chưa chắc được `LambdaMetafactory.metafactory` chấp nhận. Metafactory có hợp đồng chặt hơn, đặc biệt ở **return type của factory, arity, subtype specialization và direct implementation handle**.

### Ví dụ 3: `LambdaConversionException`

Lưu **`LinkageFailuresDemo.java`**:

~~~java
import java.lang.invoke.*;

public class LinkageFailuresDemo {
    @FunctionalInterface
    public interface Mapper<T> {
        T map(T value);
    }

    public static String combine(String prefix, String text) {
        return prefix + text;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodHandle implementation = lookup.findStatic(
                LinkageFailuresDemo.class, "combine",
                MethodType.methodType(
                        String.class, String.class, String.class));
        MethodType interfaceMethodType =
                MethodType.methodType(Object.class, Object.class);
        MethodType dynamicMethodType =
                MethodType.methodType(String.class, String.class);
        MethodType factoryType =
                MethodType.methodType(Mapper.class, String.class);

        try {
            LambdaMetafactory.metafactory(
                    lookup, "map",
                    MethodType.methodType(String.class, String.class),
                    interfaceMethodType, implementation,
                    dynamicMethodType);
        } catch (LambdaConversionException ex) {
            System.out.println(
                    "notInterface=" + ex.getClass().getSimpleName());
        }

        try {
            LambdaMetafactory.metafactory(
                    lookup, "map",
                    MethodType.methodType(Mapper.class),
                    interfaceMethodType, implementation,
                    dynamicMethodType);
        } catch (LambdaConversionException ex) {
            System.out.println(
                    "wrongArity=" + ex.getClass().getSimpleName());
        }

        try {
            LambdaMetafactory.metafactory(
                    lookup, "map", factoryType,
                    interfaceMethodType, implementation,
                    MethodType.methodType(Object.class, Object.class));
        } catch (LambdaConversionException ex) {
            System.out.println(
                    "wrongSpecialization=" +
                    ex.getClass().getSimpleName());
        }

        MethodHandle indirect = MethodHandles.insertArguments(
                implementation, 0, "Hi-");
        try {
            LambdaMetafactory.metafactory(
                    lookup, "map",
                    MethodType.methodType(Mapper.class),
                    interfaceMethodType, indirect,
                    dynamicMethodType);
        } catch (LambdaConversionException ex) {
            System.out.println(
                    "notDirect=" + ex.getClass().getSimpleName());
        }
    }
}
~~~

~~~sh
javac --release 17 LinkageFailuresDemo.java
java LinkageFailuresDemo
~~~

**Stdout:**

~~~text
notInterface=LambdaConversionException
wrongArity=LambdaConversionException
wrongSpecialization=LambdaConversionException
notDirect=LambdaConversionException
~~~

Giải thích bốn lỗi:

1. **`notInterface`:** `factoryType` trả `String` chứ không trả interface; vi phạm điều kiện của return type `Rd`.
2. **`wrongArity`:** `factoryType=()Mapper` cho `K=0`, nhưng SAM có `N=1` và implementation có `M=2`. `K+N!=M`.
3. **`wrongSpecialization`:** `dynamicMethodType=(Object)Object`, trong khi implementation argument còn lại là `String`. Dạng `Object` của tham số SAM không đủ quan hệ kiểu để satisfy điều kiện adaptation tới implementation String.
4. **`notDirect`:** `MethodHandles.insertArguments` tạo adapter đã bind prefix; handle này có thể được gọi riêng, nhưng **không phải direct method handle tham chiếu trực tiếp method/constructor** theo yêu cầu của `metafactory`. Dù đã sửa arity thành `K=0,N=1,M=1`, directness vẫn sai.

Dấu hiệu quan trọng: một phương thức Java “có thể được gọi” không đồng nghĩa nó là **direct implementation method handle** hợp lệ cho metafactory. Khi cần capture một giá trị, hãy thể hiện nó bằng **factoryType parameter** (`K`) thay vì truyền một handle đã `bindTo`/`insertArguments` tùy tiện như implementation. Nếu không phù hợp với hạn chế của metafactory, cân nhắc thiết kế một bridge method có địa chỉ trực tiếp rồi tạo handle bằng `findStatic`/`findVirtual`.

**Trong chương trình compiler tạo ra**, exception từ BSM xảy ra ở linkage có thể được JVM báo dưới dạng `BootstrapMethodError` với nguyên nhân gốc. Trong ví dụ này ta **gọi trực tiếp API `metafactory`**, nên bắt thẳng `LambdaConversionException`. Đây là hai ngữ cảnh lỗi khác nhau; đừng dùng một loại exception để giải thích mọi trường hợp.

## 10. Vì sao lỗi runtime có thể xuất hiện dù linkage đã thành công?

Giả sử interface là `Mapper<String>`:

~~~java
Mapper<String> mapper = ...;
String value = mapper.map("Ada");
~~~

Generic `T=String` giúp compiler phát hiện các phép gọi sai kiểu. Nhưng ở mức bytecode, method erased vẫn là `map(Object):Object`. Nếu code dùng raw interface hoặc unchecked cast:

~~~java
Mapper raw = mapper;
Object value = raw.map(Integer.valueOf(42));
~~~

**Đây là snippet minh họa, không độc lập**, và ví dụ 1 đã chạy trường hợp này. Đối số `Integer` đi qua erased SAM descriptor như `Object`, nhưng runtime type không phù hợp `dynamicMethodType=(String)String`. Function object kiểm tra type/cast trước khi gọi implementation, nên có thể ném `ClassCastException`.

Khi điều tra, phải phân biệt:

| Giai đoạn | Kiểu/giá trị được kiểm tra | Lỗi thường gặp |
| --- | --- | --- |
| **Bootstrap/linkage** | Factory return interface, K+N=M, direct handle, quan hệ interface/dynamic/implementation type | `LambdaConversionException`, hoặc `BootstrapMethodError` ở mức indy |
| **Capture** | K captured values thực tế, đủ kiểu cho factory target, instance receiver hợp lệ | `WrongMethodTypeException` nếu gọi MH factory sai descriptor; lỗi null receiver |
| **SAM invocation** | N đối số của `apply`/`map`/`applyAsInt` với dynamic method type và implementation | `ClassCastException`, lỗi unboxing/logic của implementation |
| **Target body** | Mã trong method/constructor implementation | Các exception mà implementation tự ném |

Không thay `dynamicMethodType` thành `(Object)Object` chỉ để tránh cast nếu implementation thực sự cần `String`. Việc đó có thể vi phạm linkage invariants hoặc làm sai hợp đồng của functional interface.

## 11. Liên hệ với nối chuỗi: `StringConcatFactory` không dùng bộ bốn kiểu của lambda

Cùng một chủ đề “Lambda và nối chuỗi”, nhưng `StringConcatFactory` dùng **một hợp đồng khác**. Compiler hiện đại có thể phát sinh indy cho `"value=" + x`, nhưng BSM tương ứng thường là:

~~~java
StringConcatFactory.makeConcat(
    MethodHandles.Lookup lookup,
    String name,
    MethodType concatType
);

StringConcatFactory.makeConcatWithConstants(
    MethodHandles.Lookup lookup,
    String name,
    MethodType concatType,
    String recipe,
    Object... constants
);
~~~

Đây là **chữ ký API để so sánh**, không phải các hàm cần tự khai báo. `concatType` là kiểu của call site trực tiếp thực hiện **nối chuỗi**, ví dụ `(String,int)String`; không tạo functional interface object và không có bốn trường `factoryType/interfaceMethodType/implementation/dynamicMethodType` của `LambdaMetafactory`.

`recipe` có các vị trí đặc biệt trong chuỗi:

- Ký tự `\1`: tiêu thụ một **dynamic argument** của call site.
- Ký tự `\2`: tiêu thụ một **constant static bootstrap argument**.
- Các ký tự thường: ghép nguyên văn.

Số `\1` phải khớp số argument động của `concatType`, và số `\2` phải khớp số constants (theo hợp đồng makeConcatWithConstants). Đừng gọi recipe là `dynamicMethodType` — chúng mô tả những điều hoàn toàn khác.

### Ví dụ 4: gọi trực tiếp StringConcatFactory để phân biệt

Lưu **`ConcatContractDemo.java`**:

~~~java
import java.lang.invoke.*;

public class ConcatContractDemo {
    public static void main(String[] args) throws Throwable {
        MethodType concatType = MethodType.methodType(
                String.class, String.class, int.class);

        CallSite site = StringConcatFactory.makeConcatWithConstants(
                MethodHandles.lookup(), "makeConcatWithConstants",
                concatType, "\1 + \1");

        String result = (String)
                site.getTarget().invokeExact("Ada", 7);

        System.out.println("concatType=" + site.type());
        System.out.println("result=" + result);
    }
}
~~~

~~~sh
javac --release 17 ConcatContractDemo.java
java ConcatContractDemo
~~~

**Stdout:**

~~~text
concatType=(String,int)String
result=Ada + 7
~~~

`"Ada"` và `7` là **dynamic call arguments** của concat target; recipe `"\1 + \1"` có hai placeholders đúng với `concatType`. Không có `Function`/`Supplier` hay SAM interface nào.

**Đây là lời gọi factory API trực tiếp**, chưa chứng minh bytecode của chương trình này có một indy site liên quan tới việc nối `"Ada"` và `7`. Muốn quan sát một compiler-generated **invokedynamic concat thật**, hãy chạy `javap -v -p CompiledLambdaTypesDemo` ở phần 6; trong môi trường `javac --release 17` được kiểm tra, nó hiển thị các call site `makeConcatWithConstants`. Cách compiler tạo concat có thể thay đổi theo JDK/flags.

Bảng phân biệt:

| Tiêu chí | `LambdaMetafactory` | `StringConcatFactory` |
| --- | --- | --- |
| Call site làm gì? | Trả functional interface object | Trực tiếp trả kết quả nối chuỗi |
| Implicit method type | `factoryType`, thường `()Function` hoặc `(String)Function` | `concatType`, ví dụ `(String,int)String` |
| Static args điển hình | `interfaceMethodType`, direct `implementation`, `dynamicMethodType` | `recipe` và có thể có `constants` |
| Có SAM method invocation về sau không? | Có | Không |
| Capture runtime values để giữ cho function object? | Có thể | Không có lambda capture theo protocol này |

Đây là lý do không nên lấy bốn tên kiểu của `LambdaMetafactory` áp dụng cho mọi `invokedynamic`. `invokedynamic` là cơ chế chung; **bootstrap method cụ thể mới định nghĩa giao thức metadata và mục đích liên kết**.

## 12. Một số điểm nâng cao: bridge methods và `altMetafactory`

`LambdaMetafactory.metafactory` là biến thể chuẩn, đủ cho nhiều lambda đơn giản. `altMetafactory` mở rộng protocol bằng các flags như:

- `FLAG_BRIDGES`: sinh thêm method signatures cần thiết để cùng một hành vi có thể được gọi qua nhiều VM descriptors (ví dụ bridge cho một số quan hệ generic/covariant).
- `FLAG_MARKERS`: thêm các marker interfaces thích hợp.
- `FLAG_SERIALIZABLE`: yêu cầu function object theo protocol serializable (có thêm quy tắc/giới hạn).

`altMetafactory` vẫn có ba static thành phần cơ bản tương ứng `interfaceMethodType`, `implementation`, `dynamicMethodType`, rồi thêm `flags` và metadata tùy flags. Nhiều method signatures không biến `factoryType` thành SAM invocation type; nó vẫn chỉ ra **factory call site**.

**Đừng dựa vào tên class runtime của lambda để hiểu generic type.** Lớp triển khai có thể là hidden class hoặc dạng được JVM tối ưu; identity, binary name và chi tiết class file không phải API ổn định. Hãy suy từ `BootstrapMethods`/`InvokeDynamic`, bốn kiểu và functional interface method đã công bố.

Tương tự, function object tạo từ lambda không mặc định bảo đảm identity giữa hai lần capture. Không dùng `==` hoặc `System.identityHashCode` như điều kiện logic khi các object được tạo từ cùng một lambda expression.

## 13. Checklist đọc một `javap -v -p`

Khi gặp dòng bytecode kiểu:

~~~text
invokedynamic ... apply:(Ljava/lang/String;)Ljava/util/function/Function;
~~~

hãy làm theo trình tự:

1. **Đọc tên và descriptor ngay tại `InvokeDynamic`**. `apply` là `interfaceMethodName`; descriptor `(String)Function` là `factoryType`. Nó nói có một captured `String` và trả một `Function`.
2. **Lần theo chỉ số bootstrap trong `BootstrapMethods`**. Kiểm tra có phải `LambdaMetafactory.metafactory` hay một BSM khác.
3. **Static arg thứ nhất:** đọc `MethodType` tương ứng `interfaceMethodType`, thường `(Object)Object` đối với `Function.apply`.
4. **Static arg thứ hai:** đọc `MethodHandle` của `implementation`; xem `REF_invokeStatic`/`REF_invokeVirtual`/`REF_newInvokeSpecial` và đầy đủ descriptor. Nếu là virtual handle, nhớ receiver ở vị trí đầu của handle.
5. **Static arg thứ ba:** đọc `dynamicMethodType` — tên trong output/tài liệu thường là *instantiatedMethodType*. Nó mô tả specialization để kiểm tra runtime, không bao gồm captured args.
6. **Đếm K,N,M.** Nếu `K=1,N=1` thì implementation cần 2 tham số, trừ những tình huống không thỏa protocol (sẽ không link).
7. **Kiểm tra erased vs instantiated.** `(Object)Object` và `(String)String` có thể khác nhau hợp lệ. Kiểu `String` phải specialize tương thích với `Object`.
8. **Xác định capture value từ bytecode trước indy.** Ví dụ `aload_0` đưa captured prefix lên stack; nó **không** nằm trong ba static args.
9. **Phân biệt call site với SAM invocation.** `invokedynamic` tạo `Function`; `invokeinterface Function.apply` về sau mới gọi behavior.
10. **Nếu còn lỗi**, xác định đó là linkage (`LambdaConversionException`/`BootstrapMethodError`), capture (`WrongMethodTypeException`/input), invocation (`ClassCastException`), hay exception do implementation body ném.

### Tránh những diễn giải sai

- “`factoryType` là chữ ký của method implementation.” — Sai: đây là chữ ký **factory**.
- “`interfaceMethodType` chứa các generic types ở Java source.” — Sai trong trường hợp generic erasure: thường là `Object`.
- “`dynamicMethodType` chứa cả captured prefix.” — Sai: nó mô tả **SAM invocation** sau specialization.
- “`implementation` luôn bằng `dynamicMethodType`.” — Sai nếu có captures hoặc instance receiver khác vai trò.
- “Implementation của `String::length` có 0 tham số.” — Sai cho virtual MethodHandle: receiver được tính.
- “Static BSM arguments chính là captured variables của lambda.” — Sai: static args là metadata linkage; capture là runtime input của factory.
- “Có thể đưa một handle qua `insertArguments` rồi luôn dùng làm `implementation` của metafactory.” — Sai: standard metafactory yêu cầu direct handle.
- “Mọi handle mà `invoke` gọi được đều dùng được cho metafactory.” — Sai: protocol có invariant và access constraints chặt.
- “`LambdaMetafactory` luôn chạy lại mỗi khi `f.apply(...)`.” — Sai: BSM dùng để link site; SAM invocation là giai đoạn khác.
- “Một lambda không capture luôn tạo object mới mỗi lần.” — Không được đảm bảo: metafactory có thể tái sử dụng object.
- “`StringConcatFactory` cũng có `interfaceMethodType` và `dynamicMethodType`.” — Sai: nó có `concatType` và protocol recipe/constant riêng.

## 14. Bài tập tự kiểm tra

**Câu 1.** `Function<String,String> f = MyClass::upper` không capture, `upper(String)String`. Bốn thành phần là gì?

**Đáp án:** `factoryType=()Function`, `interfaceMethodType=(Object)Object`, `implementation=(String)String` direct MH, `dynamicMethodType=(String)String`.

**Câu 2.** Với `text -> prefix + text`, prefix là `String` captured; SAM `Function<String,String>`. `implementation` là `(String,String)String`. Hãy tính K,N,M.

**Đáp án:** `K=1`, `N=1`, `M=2`, nên `K+N=M`. `factoryType=(String)Function`, `dynamicMethodType=(String)String`.

**Câu 3.** Vì sao `FactoryType=(String)Function` không có parameter String đại diện `text` cũng là SAM argument?

**Đáp án:** Factory chỉ nhận prefix lúc **capture** và trả Function object. `text` được nhận **sau đó** bởi `Function.apply`; nó thuộc `dynamicMethodType`/implementation phần invocation.

**Câu 4.** Một `implementation` có kiểu `(String)int` từ `findVirtual(String.class,"length",()int)`, dùng làm `String::length` với `ToIntFunction<String>`. Vì sao M bằng 1?

**Đáp án:** Receiver String được tính là tham số đầu của virtual MethodHandle dù method `length()` không có source parameters. `K=0,N=1,M=1`.

**Câu 5.** Vì sao `interfaceMethodType` của `Mapper<String>.map(String)` vẫn có thể là `(Object)Object`?

**Đáp án:** Đây là method descriptor của `Mapper<T>.map(T)` sau generic erasure. `dynamicMethodType=(String)String` mô tả specialization để kiểm tra kiểu lúc gọi.

**Câu 6.** `factoryType=()Mapper`, SAM có một tham số, implementation có hai tham số: có hợp lệ không?

**Đáp án:** Không, vì `K=0,N=1,M=2`, vi phạm `K+N=M`. Cần capture một giá trị hoặc thiết kế implementation khác.

**Câu 7.** Nếu `implementation` được tạo bằng `MethodHandles.insertArguments(...)` để bind sẵn prefix, standard `LambdaMetafactory.metafactory` chắc chắn nhận không?

**Đáp án:** Không. Standard metafactory yêu cầu **direct method handle**. Adapter do combinator tạo ra không tự thỏa ràng buộc directness.

**Câu 8.** `Function` object được tạo thành công, nhưng raw `Function.apply(42)` ném `ClassCastException`. Điều đó chứng tỏ BSM link sai chứ?

**Đáp án:** Không. Erased interface method nhận Object, nhưng `dynamicMethodType` có thể yêu cầu String; check runtime từ chối Integer.

**Câu 9.** Trong `javap`, vì sao `factoryType` nằm trong `InvokeDynamic` còn ba phần còn lại nằm trong `BootstrapMethods`?

**Đáp án:** Factory type là method descriptor của chính call site, được JVM chuyển thành implicit BSM argument; `interfaceMethodType`, `implementation`, `dynamicMethodType` là **ba static bootstrap arguments** của LambdaMetafactory.

**Câu 10.** `StringConcatFactory.makeConcatWithConstants` có thể trả `(String,int)String`. Đây có phải `factoryType` tạo `Function` không?

**Đáp án:** Không. Đó là `concatType` của call site trực tiếp nối chuỗi; nó không có SAM interface/implementation/dynamicMethodType theo contract lambda.

## 15. Tài liệu chính thống

- Java SE 17, `LambdaMetafactory` — ba phases, bốn tham số chính, K/N/M, adaptation và linkage invariants: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/LambdaMetafactory.html
- Java SE 17, `MethodType` — tham số, return type và cách viết chữ ký method handles: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html
- Java SE 17, `MethodHandles.Lookup` — `findStatic`, `findVirtual` và lookup privileges: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html
- Java SE 17, `MethodHandle` — direct handles, `invokeExact`, `invoke`, adapters và type: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html
- Java SE 17, `CallSite` — factory target và type của call site: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/CallSite.html
- Java SE 17, `StringConcatFactory` — concatType, recipe, static constants, khác biệt với lambda metafactory: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/StringConcatFactory.html
- JVMS 17, `4.7.23` — `BootstrapMethods` attribute, liên kết static arguments: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.23
- JVMS 17, `5.4.3.6` — dynamically-computed call site resolution: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.3.6

**Kết luận:** `factoryType` quyết định **factory nhận captured values và trả functional object nào**; `interfaceMethodType` quyết định **chữ ký SAM ở mức JVM**; `implementation` chỉ ra **method/constructor thực thi hành vi với K+N tham số**; `dynamicMethodType` quyết định **chữ ký SAM sau specialization được kiểm tra khi invocation**. Nhớ ba giai đoạn **linkage → capture → invocation** và công thức **`K+N=M`** sẽ giúp giải mã `javap`, sửa `LambdaConversionException` và phân biệt chính xác lambda metafactory với string-concat bootstrap.