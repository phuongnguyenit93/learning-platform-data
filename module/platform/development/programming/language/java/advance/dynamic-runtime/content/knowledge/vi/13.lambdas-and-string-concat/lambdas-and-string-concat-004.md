# 13.4 Ràng buộc direct method handle, kiểu tham số và kiểu trả về của metafactory

**Module:** Java Advance - dynamic-runtime  
**Chủ đề cha:** 13. Lambda và nối chuỗi  
**API trọng tâm:** `java.lang.invoke.LambdaMetafactory.metafactory`, `MethodHandle`, `MethodType` và `CallSite`  
**Môi trường:** Java 17+.

## Mục tiêu

`LambdaMetafactory` phục vụ cơ chế tạo function object cho lambda expression và method reference. Nó liên kết một **direct method handle** với một functional interface, có thể cố định một số đối số khi tạo object (capture), và chỉ cho phép những tổ hợp kiểu tham số/trả về đáp ứng một bộ điều kiện chính xác.

Sau bài này, bạn có thể:

1. Phân biệt **`factoryType`**, **`interfaceMethodType` (SAM)**, **`implementation.type()`** và **`dynamicMethodType` (instantiated)**.
2. Giải thích vì sao implementation cần một **direct MethodHandle** đến method/constructor, không được lấy arbitrary adapter làm implementation.
3. Tính và kiểm tra `K+N=M`, captured type equality `D_i=A_i`, parameter adaptation và return adaptation của metafactory.
4. Phân biệt ba giai đoạn **linkage → capture → invocation**, cùng lỗi xuất hiện ở từng giai đoạn.
5. Viết Java 17+ có lambda capture, non-capture, receiver method reference, generic SAM và return `void`; kiểm thử những trường hợp bị từ chối.
6. Nhận ra bootstrap `LambdaMetafactory` của `invokedynamic` trong `javap` mà không nhầm với bootstrap nối chuỗi `StringConcatFactory`.

## 1. Metafactory tạo ra cái gì?

Xét một lambda:

~~~java
java.util.function.Function<String, String> f =
        value -> "[" + value + "]";
~~~

Compiler có thể hạ lambda thành một `invokedynamic` dẫn đến bootstrap `LambdaMetafactory.metafactory`. Kết quả liên kết là một `CallSite`. **Target của CallSite là một factory handle tạo function object**, còn `implementation` được truyền vào metafactory là direct handle chứa logic chạy khi functional method được gọi.

~~~text
Lambda / method reference trong Java
        |
        v
javac sinh invokedynamic + bootstrap information
        |
        v
JVM liên kết -> LambdaMetafactory.metafactory(...)
        |
        v
CallSite, type = factoryType
        |
        +-- target: factory MethodHandle
                      |
                      | CAPTURE: truyền K giá trị captured
                      v
              function object implements functional interface
                      |
                      | INVOCATION: truyền N tham số của SAM
                      v
              direct implementation method/constructor
~~~

Một factory không capture có type ví dụ `()TextOp`. Một factory capture `prefix` có type `(String)TextOp`. Cả hai đều **trả đối tượng hàm**, không trả kết quả trực tiếp của method triển khai. Cần tiếp tục gọi `TextOp.apply(...)` để thực thi logic.

Metafactory có thể sinh class tại runtime hoặc tái dùng một class phù hợp. Không được giả định tên class/identity của lambda object là ổn định, cũng không dùng `==` của hai lambda object làm hợp đồng nghiệp vụ.

## 2. Sáu tham số của `LambdaMetafactory.metafactory`

Chữ ký API được trình bày để học:

~~~java
public static CallSite metafactory(
        MethodHandles.Lookup caller,
        String interfaceMethodName,
        MethodType factoryType,
        MethodType interfaceMethodType,
        MethodHandle implementation,
        MethodType dynamicMethodType
) throws LambdaConversionException;
~~~

Đây là chữ ký mô tả API, **không phải mã để viết lại class của JDK**. Một số tài liệu dùng tên tương đương `invokedType`, `samMethodType`, `implMethod`, `instantiatedMethodType`.

| Tham số | Chức năng | Ví dụ |
| --- | --- | --- |
| `caller` | `Lookup` của bên tạo hàm; phải có **full privilege access** | `MethodHandles.lookup()` trong class hợp lệ |
| `interfaceMethodName` | Tên phương thức functional interface phải implement | `"apply"` |
| `factoryType` | MethodType của target CallSite: nhận captured arguments, trả interface | `(String)TextOp` |
| `interfaceMethodType` | MethodType method SAM sẽ được implement | `(String)String` |
| `implementation` | **Direct** handle trỏ đến method/constructor triển khai | `join(String,String)String` |
| `dynamicMethodType` | Instantiated MethodType kiểm tra ở invocation | `(String)String` |

### 2.1. `MethodType` được viết theo thứ tự nào?

~~~java
MethodType factoryType =
        MethodType.methodType(TextOp.class, String.class);
MethodType samType =
        MethodType.methodType(String.class, String.class);
MethodType implType =
        MethodType.methodType(
                String.class, String.class, String.class);
~~~

Đoạn này giả định `TextOp` đã có trong scope; nó không phải file độc lập. Với `MethodType.methodType(returnType, parameters...)`, **kiểu trả về ở vị trí đầu tiên**, khác cách đọc danh sách tham số trong Java source:

~~~text
factoryType = (String)TextOp
samType     = (String)String
implType    = (String,String)String
~~~

Sai thứ tự trong `methodType(...)` có thể khiến `Lookup.findStatic` không tìm thấy method, hoặc metafactory từ chối linkage.

### 2.2. Factory type và implementation type không phải một

Nếu implementation là:

~~~java
static String join(String prefix, String value) {
    return prefix + value;
}
~~~

Đây là phương thức minh họa đặt trong một class. Factory nhận `prefix` rồi trả `TextOp`. Một lần gọi `TextOp.apply(value)` mới cung cấp `value` cho implementation. Cú pháp tương ứng khi có CallSite:

~~~java
TextOp op = (TextOp) site.getTarget().invokeExact("pre:");
String output = op.apply("java");
~~~

Đoạn này cũng là minh họa trong scope có `site` và `TextOp`. `site.getTarget().type()` là `(String)TextOp`; **không** phải `(String,String)String` của implementation. Khi gọi factory bằng `invokeExact`, cả **kiểu đối số capture và return cast** tại nơi gọi phải đúng factory type.

## 3. Ký hiệu K, N, M và bốn MethodType

Đặt các kiểu như Javadoc Java SE 17:

| Loại | Cấu trúc | Ý nghĩa |
| --- | --- | --- |
| `factoryType` | `(D1,...,Dk) Rd` | K captured arguments, return `Rd` là interface |
| `interfaceMethodType` | `(U1,...,Un) Ru` | N parameters của SAM |
| `implementation.type()` | `(A1,...,Am) Ra` | M parameters của method thực thi |
| `dynamicMethodType` | `(T1,...,Tn) Rt` | N parameters và return của instantiated SAM |

Với `String join(String prefix,String value)` và `TextOp.apply(String)String`:

~~~text
factoryType        = (String)TextOp          K=1
interfaceMethodType= (String)String          N=1
implementation     = (String,String)String   M=2
dynamicMethodType  = (String)String          N=1
K+N=M              = 1+1=2                  true
~~~

**Các ràng buộc linkage chính xác:**

1. **`Rd` phải là interface** mà function object implement. `factoryType` trả `String` hoặc một class thường là sai.
2. **`implementation` phải là direct method handle** chỉ đến một method hoặc constructor.
3. `interfaceMethodType` và `dynamicMethodType` có **cùng số tham số N**. Với từng vị trí `i`, `Ti == Ui`, hoặc cả hai là reference types và `Ti` là subtype của `Ui`.
4. Kiểu trả `Rt == Ru`, hoặc cả hai là reference types và `Rt` là subtype của `Ru`.
5. **`K + N = M`**. Captured parameters và invocation parameters phải đúng tổng số đối số implementation.
6. Với các captured parameters đầu của implementation: **`Di = Ai`** với `i=1..K`, yêu cầu **type equality** chứ không chỉ subtype.
7. Với invocation parameters: **`Ti` adaptable sang `A(K+i)`** theo quy tắc của metafactory.
8. Với kiểu trả về: **`Rt == void`**, hoặc `Ra != void` và **`Ra` adaptable sang `Rt`**.
9. Nếu implementation là **instance method** và có captured arguments (`K>0`), captured argument đầu tiên đóng vai trò receiver **phải non-null** theo hợp đồng API.

Không được thay các điều kiện này bằng trực giác “kiểu value runtime trông phù hợp”. Các điều kiện phần lớn được kiểm tra ngay khi **linkage**, trước khi có function object.

### 3.1. Captured types khớp **chính xác**

Ví dụ sai:

~~~text
factoryType           = (Object)TextOp
interfaceMethodType   = (String)String
implementation.type() = (String,String)String
dynamicMethodType     = (String)String
~~~

`D1=Object` nhưng `A1=String`; do đó điều kiện `D1=A1` sai, **`LambdaConversionException`** xuất hiện khi liên kết. Dù runtime có truyền `"pre:"` (một String) vào factory, compiler đã mô tả captured parameter type là `Object` nên không cứu được.

Để đúng, đặt factory captured type là `String`, hoặc viết một **direct helper method** thực sự nhận Object ở vị trí capture và xử lý việc ép kiểu bên trong.

### 3.2. Sai số lượng tham số không được sửa nhờ varargs

Nếu implementation có `M=2`, SAM có `N=1`, nhưng factory không capture gì `K=0` thì `K+N=M` thành `0+1≠2`. Metafactory từ chối. Nó không tự động đóng gói/giải nén varargs để bù số đối số thiếu.

Với một direct handle trỏ đến instance method, `MethodHandle.type()` đã chứa **receiver** như tham số đầu; phải tính nó vào `M`. Receiver có thể nằm trong `K` (được capture khi factory chạy) hoặc nằm trong `N` (được SAM truyền lúc invocation) nếu chữ ký interface phù hợp.

### 3.3. Return type là một phần độc lập của hợp đồng

Nếu instantiated SAM yêu cầu `String` mà implementation trả `int`, không có phép adaptation phù hợp từ primitive int thành String. Ngược lại, nếu instantiated type trả `void`, metafactory có thể chấp nhận một implementation trả giá trị và **bỏ giá trị đó**. Phân biệt:

~~~text
SAM:        (String)void
impl:       (String)String
instantiated:(String)void   -> có thể hợp lệ, discard return

SAM:        (String)String
impl:       (String)void
instantiated:(String)String -> không thể tự tạo String return
~~~

Quy tắc này không đồng nghĩa “return type tùy ý”; hướng adaptation của giá trị trả về phải được xét theo Javadoc.

## 4. Direct MethodHandle: ràng buộc không thể bỏ qua

### 4.1. Direct handle và adapter handle

Một `Lookup` thích hợp tạo direct handle tới member:

~~~java
MethodHandle directStatic = lookup.findStatic(
        MetafactoryContractDemo.class, "upper",
        MethodType.methodType(String.class, String.class));

MethodHandle directVirtual = lookup.findVirtual(
        Prefixer.class, "join",
        MethodType.methodType(String.class, String.class));
~~~

Đây là đoạn minh họa bên trong `MetafactoryContractDemo` ở mục 8. `directStatic.type()=(String)String`. `directVirtual.type()=(Prefixer,String)String` do handle của instance method có receiver ở parameter đầu.

`Lookup.findConstructor` cũng tạo direct handle cho constructor, với return type của handle là class được tạo. Một số handle từ `Lookup.unreflect` có thể là direct reference nếu quyền truy cập cho phép.

Một **adapter handle**, dù gọi được và có type đúng, **không mặc nhiên** là direct handle:

~~~java
MethodHandle bound = MethodHandles.insertArguments(
        join, 0, "bound:");
~~~

`join` là direct `(String,String)String`. `bound` là adapter `(String)String` có một argument bind sẵn. Nếu truyền `bound` vào `metafactory` như implementation, nó bị từ chối vì **không direct** (được kiểm chứng trong demo). Các combinator khác như `filterArguments`, `guardWithTest`, `bindTo` và `asType` thường tạo adapter, không tự biến pipeline thành direct member reference.

**Không nhận diện direct chỉ bằng type.** Một phép chuyển đổi không làm thay type có thể trả lại chính handle cũ trong một số trường hợp; việc type bằng nhau vẫn không chứng minh bản chất direct của handle.

### 4.2. Cách sửa đúng khi đã bind trước đối số

Không dùng `insertArguments(join, 0, "pre:")` rồi ép metafactory chấp nhận. Hãy để metafactory xử lý capture:

~~~java
CallSite site = LambdaMetafactory.metafactory(
        lookup, "apply",
        MethodType.methodType(TextOp.class, String.class),
        MethodType.methodType(String.class, String.class),
        join,
        MethodType.methodType(String.class, String.class));
TextOp op = (TextOp) site.getTarget().invokeExact("pre:");
~~~

Ở đây `join` vẫn direct, và factory type diễn tả **capture prefix** chính xác. Đoạn này giả định `lookup`, `join` và `TextOp` tồn tại như demo đầy đủ.

Nếu pipeline đã được tạo bằng nhiều combinator mà cần functional API, cân nhắc **direct helper method** gọi pipeline theo một contract rõ ràng, hoặc chỉ dùng MethodHandle/adapter thay vì dùng `LambdaMetafactory` như công cụ tổng quát.

### 4.3. Cách quan sát direct handle

`Lookup.revealDirect(handle)` có thể trả `MethodHandleInfo` khi handle thật sự direct và lookup có quyền crack handle; với adapter không direct thì kiểm tra này không thành công. Đây là công cụ **chẩn đoán**, không biến một adapter thành direct.

Ngoài tính direct, `caller` của metafactory phải có **full privilege access**. `MethodHandles.publicLookup()` chỉ cho phép truy cập public member theo giới hạn của nó, nên không thỏa điều kiện caller ở đây; demo kiểm chứng `LambdaConversionException`. Đừng dùng metafactory để vượt rào `private`, package access hoặc JPMS module.

## 5. Ba thời điểm của một hàm sinh bởi metafactory

### 5.1. Linkage

`LambdaMetafactory.metafactory(...)` nhận lookup, tên method, các MethodType và direct handle; kiểm tra contract và trả một `CallSite`. Có thể xảy ra việc sinh class hoặc tái sử dụng class do runtime kiểm soát.

Với việc gọi API trực tiếp, sai liên kết thường báo **`LambdaConversionException`**. Nếu metafactory được gọi làm bootstrap của một instruction `invokedynamic`, lỗi của bootstrap/resolution có thể hiển thị thành **`BootstrapMethodError`** từ phía instruction.

### 5.2. Capture

~~~java
TextOp first  = (TextOp) site.getTarget().invokeExact("pre:");
TextOp second = (TextOp) site.getTarget().invokeExact("tag:");
~~~

Đây là đoạn minh họa với site `(String)TextOp`. Mỗi lời gọi factory cung cấp K captured values. Mọi giá trị đó sẽ được function object dùng khi SAM được gọi.

Đối với instance direct handle và receiver được capture, tài liệu yêu cầu receiver khác `null`. **Không dựa vào một thời điểm ném NPE cụ thể** để kiểm tra hợp đồng: JVM/runtime có thể chỉ bộc lộ lỗi khi cố gọi method; nên validate receiver trước khi capture nếu API cần rõ ràng.

### 5.3. Invocation

~~~java
System.out.println(first.apply("java"));
System.out.println(second.apply("java"));
~~~

Khi gọi SAM, implementation nhận **captured arguments đứng trước**, sau đó mới đến **invocation arguments**. Ví dụ với `join(String prefix,String value)`:

~~~text
factory("pre:") -> giữ prefix
    -> apply("java") -> join("pre:", "java")
    -> "pre:java"
~~~

Nếu SAM là generic-erased và instantiated type hẹp hơn, adapter có thể cast ở invocation. Linkage hợp lệ không có nghĩa mọi object runtime do raw caller truyền đều hợp lệ.

## 6. Generic SAM và kiểu instantiated

`java.util.function.Function<T,R>` có source method `R apply(T value)` nhưng sau erasure chữ ký runtime của SAM là `(Object)Object`. Với `Function<String,String>`, instantiated method type có thể là `(String)String`.

~~~text
factoryType          = ()Function
interfaceMethodType  = (Object)Object
implementation.type  = (String)String
dynamicMethodType    = (String)String
~~~

Các điều kiện:

- `K=0`, `N=1`, `M=1`.
- SAM `U1=Object`, instantiated `T1=String`: reference subtype hợp lệ.
- SAM return `Ru=Object`, instantiated return `Rt=String`: subtype hợp lệ.
- Invocation `T1=String` adaptable sang implementation parameter `A1=String`; return `Ra=String` adaptable sang `Rt=String`.

Một `Function<String,String>` sử dụng đúng generics sẽ chỉ nhận String từ source compile-time. Nhưng nếu mã dùng **raw Function** rồi truyền `Integer`, adapter có thể ném **`ClassCastException`** ở invocation. Đây là lỗi **khác** `LambdaConversionException` tại linkage.

### 6.1. Instantiated type không thể tùy ý “đổi tên” kiểu

Một SAM `(String)String` và instantiated `(Integer)String` **không** đạt quy tắc Ti bằng Ui hoặc Ti subtype Ui, vì Integer không là subtype của String. Cả hai cùng là Object ở cấp cha không đủ để link.

### 6.2. Quy tắc thích nghi Q sang S

Javadoc Java 17 định nghĩa bảng adaptability cụ thể:

| Nguồn Q → đích S | Khả năng thích nghi chung | Ghi chú |
| --- | --- | --- |
| Primitive → primitive | Widening primitive hợp lệ, ví dụ `int → long` | Không tùy ý narrowing |
| Primitive → reference | Boxing theo quan hệ wrapper phù hợp | Không phải mọi reference type đều chấp nhận mọi primitive |
| Reference → primitive | Có thể unboxing + widening theo rule | Runtime có thể gặp cast/null failure |
| Reference → reference | Tuân theo link-time subtype check và invocation-time cast tương ứng | Link có thể qua, runtime object vẫn có thể sai kiểu |
| Implementation return → instantiated return | Adapt theo đúng hướng return; special case `Rt=void` | Không thể sinh non-void result từ implementation void |

Tính adaptable của **parameter** và của **return** không được suy diễn như một phép so sánh đối xứng. Khi một case quan trọng liên quan wrapper/primitive, dùng bảng đầy đủ trong Javadoc `LambdaMetafactory` Java 17.

Metafactory **không làm varargs adaptations** theo cách một caller Java thông thường có thể kỳ vọng; compiler hoặc helper method phải giải quyết shape trước khi link.

## 7. Method instance và captured receiver

Đối với:

~~~java
final class Prefixer {
    String join(String value) { return "obj:" + value; }
}
~~~

Đây là snippet minh họa độc lập về ý tưởng; trong demo đầy đủ, `Prefixer` giữ prefix trong field. Với `Lookup.findVirtual(Prefixer.class,"join", MethodType.methodType(String.class,String.class))`, direct handle có type:

~~~text
(Prefixer,String)String
~~~

Nếu muốn `TextOp.apply(String)String`, factory capture receiver:

~~~text
factoryType          = (Prefixer)TextOp       K=1
interfaceMethodType  = (String)String         N=1
implementation.type  = (Prefixer,String)String M=2
dynamicMethodType    = (String)String
~~~

`D1=Prefixer == A1`; `K+N=M`. Function object được tạo từ một instance Prefixer rồi nhận String lúc gọi `apply`.

Nếu **không capture receiver**, SAM phải truyền receiver như một parameter phù hợp, nghĩa là functional interface cần có chữ ký hai đối số, ví dụ `(Prefixer,String)String`. Đừng quên receiver khi đếm M chỉ vì source method định nghĩa một formal parameter `String`.

Đối với constructor direct handle, type của handle trả **instance class mới**. Khi mapping sang `Supplier<Foo>` không capture, SAM `()Foo` có thể link tới direct constructor `()Foo`; các điều kiện type/lookup vẫn phải thỏa.

## 8. Thực hành Java 17: một chương trình cho nhiều ràng buộc

Ví dụ kiểm tra cùng lúc:

- Factory có capture `prefix` và hai function objects khác nhau.
- Factory không capture, implementation direct `upper(String)String`.
- Receiver capture cho instance method `Prefixer.join`.
- `Function<String,String>` với SAM erased `(Object)Object`.
- Return `void` của `Sink.accept` có thể bỏ return `String` từ implementation.
- Sáu lỗi cấu hình kiểu/handle và một lỗi lookup privilege, tất cả được quan sát ở linkage.

**Tệp độc lập:** `MetafactoryContractDemo.java`

~~~java
import java.lang.invoke.*;
import java.util.Locale;
import java.util.function.Function;

public final class MetafactoryContractDemo {
    @FunctionalInterface
    interface TextOp { String apply(String value); }

    @FunctionalInterface
    interface Sink { void accept(String value); }

    static final class Prefixer {
        private final String prefix;
        Prefixer(String prefix) { this.prefix = prefix; }
        String join(String value) { return prefix + value; }
    }

    private static String join(String prefix, String value) {
        return prefix + value;
    }

    private static String upper(String value) {
        return value.toUpperCase(Locale.ROOT);
    }

    private static int size(String value) {
        return value.length();
    }

    private static void invalid(String label, MethodType factory, MethodType sam,
                                MethodHandle implementation, MethodType instantiated) {
        try {
            LambdaMetafactory.metafactory(
                    MethodHandles.lookup(), "apply",
                    factory, sam, implementation, instantiated);
            System.out.println(label + "=UNEXPECTED_SUCCESS");
        } catch (LambdaConversionException expected) {
            System.out.println(label + "=LambdaConversionException");
        }
    }

    @SuppressWarnings({"rawtypes", "unchecked"})
    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodType stringToString =
                MethodType.methodType(String.class, String.class);
        MethodHandle join = lookup.findStatic(
                MetafactoryContractDemo.class, "join",
                MethodType.methodType(
                        String.class, String.class, String.class));

        CallSite captured = LambdaMetafactory.metafactory(
                lookup, "apply",
                MethodType.methodType(TextOp.class, String.class),
                stringToString,
                join,
                stringToString);
        System.out.println("capturedSite=" + captured.type());
        System.out.println("capturedTarget=" + captured.getTarget().type());
        TextOp a = (TextOp) captured.getTarget().invokeExact("pre:");
        TextOp b = (TextOp) captured.getTarget().invokeExact("tag:");
        System.out.println("captureA=" + a.apply("java"));
        System.out.println("captureB=" + b.apply("java"));

        MethodHandle direct = lookup.findStatic(
                MetafactoryContractDemo.class, "upper", stringToString);
        CallSite none = LambdaMetafactory.metafactory(
                lookup, "apply", MethodType.methodType(TextOp.class),
                stringToString, direct, stringToString);
        TextOp upper = (TextOp) none.getTarget().invokeExact();
        System.out.println("noCapture=" + upper.apply("java"));

        MethodHandle virtual = lookup.findVirtual(
                Prefixer.class, "join", stringToString);
        CallSite receiverSite = LambdaMetafactory.metafactory(
                lookup, "apply",
                MethodType.methodType(TextOp.class, Prefixer.class),
                stringToString, virtual, stringToString);
        TextOp receiver = (TextOp) receiverSite.getTarget()
                .invokeExact(new Prefixer("obj:"));
        System.out.println("instanceCapture=" + receiver.apply("java"));

        MethodType genericSam =
                MethodType.methodType(Object.class, Object.class);
        Function<String, String> fn = (Function<String, String>)
                LambdaMetafactory.metafactory(
                    lookup, "apply",
                    MethodType.methodType(Function.class),
                    genericSam, direct, stringToString)
                    .getTarget().invokeExact();
        System.out.println("generic=" + fn.apply("java"));
        try {
            Function raw = fn;
            Object ignored = raw.apply(42);
            System.out.println("genericCast=UNEXPECTED_SUCCESS:" + ignored);
        } catch (ClassCastException expected) {
            System.out.println("genericCast=ClassCastException");
        }

        MethodType voidSam =
                MethodType.methodType(void.class, String.class);
        Sink sink = (Sink) LambdaMetafactory.metafactory(
                    lookup, "accept", MethodType.methodType(Sink.class),
                    voidSam, direct, voidSam)
                    .getTarget().invokeExact();
        sink.accept("java");
        System.out.println("discardReturn=ok");

        invalid("notDirect", MethodType.methodType(TextOp.class),
                stringToString,
                MethodHandles.insertArguments(join, 0, "bound:"),
                stringToString);
        invalid("wrongArity", MethodType.methodType(TextOp.class),
                stringToString, join, stringToString);
        invalid("wrongCapture", MethodType.methodType(TextOp.class, Object.class),
                stringToString, join, stringToString);
        invalid("wrongReturn", MethodType.methodType(TextOp.class),
                stringToString,
                lookup.findStatic(MetafactoryContractDemo.class, "size",
                                  MethodType.methodType(int.class, String.class)),
                stringToString);
        invalid("wrongInstantiated", MethodType.methodType(TextOp.class),
                stringToString, direct,
                MethodType.methodType(String.class, Integer.class));
        invalid("nonInterfaceFactory", MethodType.methodType(String.class),
                stringToString, direct, stringToString);
        try {
            LambdaMetafactory.metafactory(
                    MethodHandles.publicLookup(), "apply",
                    MethodType.methodType(TextOp.class),
                    stringToString, direct, stringToString);
            System.out.println("weakLookup=UNEXPECTED_SUCCESS");
        } catch (LambdaConversionException expected) {
            System.out.println("weakLookup=LambdaConversionException");
        }
    }
}
~~~

**Biên dịch và chạy bằng JDK 17+:**

~~~bash
javac --release 17 -d out MetafactoryContractDemo.java
java -cp out MetafactoryContractDemo
~~~

`javac -d out` có thể tạo thư mục out nếu chưa tồn tại. `@SuppressWarnings` được dùng chỉ để trình biên dịch không cảnh báo về đoạn raw Function có chủ đích phục vụ minh họa.

**Stdout đã được kiểm chứng bằng đúng mã nguồn trên:**

~~~text
capturedSite=(String)TextOp
capturedTarget=(String)TextOp
captureA=pre:java
captureB=tag:java
noCapture=JAVA
instanceCapture=obj:java
generic=JAVA
genericCast=ClassCastException
discardReturn=ok
notDirect=LambdaConversionException
wrongArity=LambdaConversionException
wrongCapture=LambdaConversionException
wrongReturn=LambdaConversionException
wrongInstantiated=LambdaConversionException
nonInterfaceFactory=LambdaConversionException
weakLookup=LambdaConversionException
~~~

### 8.1. Giải thích nhóm thành công

**`capturedSite=(String)TextOp` và `capturedTarget=(String)TextOp`:** CallSite giữ target factory, cả hai đều có `factoryType`. Target **không** có `(String,String)String`, vì implementation không phải target của CallSite.

**`captureA=pre:java` / `captureB=tag:java`:** một direct method `join` nhận hai tham số, nhưng chỉ `value` đến từ SAM; `prefix` đã capture qua factory.

**`noCapture=JAVA`:** factory `()TextOp` không cần arguments. Direct implementation `upper` có một parameter cho SAM.

**`instanceCapture=obj:java`:** `findVirtual` handle chứa receiver `Prefixer` là tham số đầu. Factory bắt đầu bằng capture receiver, sau đó `apply` cung cấp String.

**`generic=JAVA`:** `Function.apply` erased nhận Object/trả Object, instantiated String/String. **`genericCast=ClassCastException`:** raw caller gửi Integer khiến runtime adapter kiểm tra giá trị thất bại; link trước đó hoàn toàn hợp lệ.

**`discardReturn=ok`:** instantiated SAM trả void, nên String do implementation `upper` trả không được đưa ra từ method `Sink.accept`.

### 8.2. Giải thích nhóm lỗi linkage

| Dòng kết quả | Nguyên nhân | Hướng sửa |
| --- | --- | --- |
| `notDirect` | `insertArguments` tạo adapter handle, không phải direct | Đưa prefix vào `factoryType`, giữ `join` direct |
| `wrongArity` | `K=0,N=1,M=2` làm `K+N≠M` | Capture một đối số hoặc chọn direct impl một tham số |
| `wrongCapture` | Factory captured `Object`, impl prefix `String` | Dùng captured `String` đúng type equality |
| `wrongReturn` | Implementation trả `int`, instantiated đòi `String` | Chọn direct method với return thích nghi |
| `wrongInstantiated` | SAM nhận `String`, instantiated nhận `Integer` | Chọn subtype/identical type đúng |
| `nonInterfaceFactory` | Factory return là class `String`, không phải interface | Trả `TextOp` hoặc interface phù hợp |
| `weakLookup` | `publicLookup` thiếu full privilege access | Dùng lookup của caller được phép |

Tất cả được in là `LambdaConversionException` nhưng bản chất khác nhau. Khi debug, đừng bắt chung rồi bỏ qua thông tin `factoryType`/`interfaceMethodType`/`implementation.type()`/`dynamicMethodType`.

## 9. `invokedynamic`, bytecode và direct implementation handle

Một ví dụ lambda có capture giúp nhìn thấy công việc của compiler.

**File độc lập:** `LambdaBytecodeView.java`

~~~java
import java.util.function.Function;

public final class LambdaBytecodeView {
    static Function<String,String> withPrefix(String prefix) {
        return value -> prefix + value;
    }

    public static void main(String[] args) {
        Function<String,String> f = withPrefix("id:");
        System.out.println(f.apply("17"));
    }
}
~~~

Biên dịch, chạy và inspect:

~~~bash
javac --release 17 -d out LambdaBytecodeView.java
java -cp out LambdaBytecodeView
javap -v -c -p -classpath out LambdaBytecodeView
~~~

Stdout:

~~~text
id:17
~~~

Tìm các cấu trúc sau trong `javap` (excerpt bỏ index/offset vì thay đổi theo artifact):

~~~text
InvokeDynamic ... apply:(Ljava/lang/String;)Ljava/util/function/Function;
BootstrapMethods:
  ... REF_invokeStatic java/lang/invoke/LambdaMetafactory.metafactory:...
  ... REF_invokeStatic LambdaBytecodeView.lambda$withPrefix$0:
      (Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String;
~~~

Giải thích:

- `withPrefix(prefix)` có factory capture một String, trả Function.
- Method tổng hợp `lambda$withPrefix$0` có thể nhận **prefix String + value String**, là direct implementation method được bootstrap tham chiếu.
- Hai đối số implementation tương ứng **K=1 capture** và **N=1 invocation**.
- Trong Java 17, phép `prefix + value` còn có thể sinh **một `invokedynamic` khác** cho string concatenation, bootstrap có thể là `StringConcatFactory`. Cùng opcode nhưng **hai protocol bootstrap khác nhau**.
- Chỉ số constant pool và tên synthetic method không phải API công khai; nội dung bytecode có thể thay đổi theo compiler. Hãy học cách nhận diện cấu trúc thay vì học thuộc tên `lambda$withPrefix$0`.

**Phân biệt:** Tự gọi `LambdaMetafactory.metafactory(...)` trong `main` như demo mục 8 là lời gọi API tĩnh, **không tự tạo một instruction `invokedynamic`** cho chính lời gọi đó. `invokedynamic` chỉ có khi compiler/bytecode generator thật sự phát hành instruction tương ứng.

## 10. Phân biệt lỗi theo thời điểm

| Giai đoạn | Lỗi thường gặp | Biểu hiện | Bước kiểm tra |
| --- | --- | --- | --- |
| Tìm implementation | Sai member name/type/access | `NoSuchMethodException`, `IllegalAccessException` | `Lookup.findStatic/findVirtual`, module visibility |
| Linkage metafactory trực tiếp | Handle không direct, sai K/N/M, wrong capture/return, thiếu full privilege | `LambdaConversionException` | Bốn MethodType + directness + Lookup |
| Linkage thông qua bytecode `invokedynamic` | Bootstrap sai, ném lỗi hoặc trả CallSite không đúng hợp đồng | `BootstrapMethodError` trong nhiều trường hợp | `javap`, BootstrapMethods, nguyên nhân lồng |
| Capture factory | `invokeExact` sai descriptor factory | `WrongMethodTypeException` | `site.getTarget().type()` |
| Capture instance receiver | Receiver null trái điều kiện API | Precondition bị vi phạm; lỗi có thể không hiện ngay khi capture | Validate receiver trước |
| Invocation generic | Runtime value không phù hợp instantiated type | `ClassCastException` | Erased SAM/instantiated, kiểu dữ liệu thực |
| Invocation implementation | Logic method đích ném lỗi | Exception của method đích | Phân biệt lỗi nghiệp vụ và lỗi linkage |

### 10.1. Quy trình kiểm tra có thể áp dụng ngay

1. Ghi `interfaceMethodName`, `factoryType`, `interfaceMethodType`, `implementation.type()`, `dynamicMethodType`, `callerLookup`.
2. Kiểm tra factory return là interface; handle implementation có **direct member reference** và lookup đủ quyền.
3. Đếm số đối số: `K + N = M`. Với instance method, tính **receiver** vào M.
4. So từng captured type `D_i=A_i`. Đừng coi Object/String là “gần bằng nhau”.
5. Kiểm tra SAM và instantiated cùng N, `Ti` đồng nhất/subtype `Ui`, `Rt` đồng nhất/subtype `Ru`.
6. Kiểm tra `Ti` adaptable sang `A(K+i)`, còn return `Ra` adaptable sang `Rt` hoặc instantiated return void.
7. Chỉ sau khi link thành công mới kiểm tra signature khi gọi factory target, captured receiver và object runtime lúc invoke SAM.

Đừng chữa `LambdaConversionException` bằng cách nuốt exception rồi sử dụng một function object chưa hề được tạo. Cần sửa linkage inputs.

## 11. Những hiểu lầm thường gặp

1. **“Handle có đúng type là direct.”** Sai. Adapter có thể đúng type mà không direct.
2. **“`insertArguments` là cách capture tương đương trong metafactory.”** Nó tạo một adapter, không thỏa direct implementation; capture đúng cách được mô tả trong factory type.
3. **“Factory target là implementation handle.”** Sai. Factory trả function object; implementation chỉ chạy lúc gọi SAM.
4. **“SAM và instantiated type luôn giống nhau.”** Sai khi generic SAM erased là Object nhưng lambda cụ thể cần String.
5. **“Captured String có thể khai báo Object vì runtime vẫn là String.”** Sai; captured type equality dùng type trong MethodType.
6. **“Có thể tự bù tham số thiếu bằng varargs.”** Sai; `K+N=M` phải đúng, varargs adaptation không tự làm ở metafactory.
7. **“Receiver của instance method không xuất hiện trong MethodType.”** Sai. `findVirtual` handle có receiver như một đối số.
8. **“Lỗi cast runtime là LambdaConversionException.”** Sai. Adapter invocation có thể ném ClassCastException sau linkage thành công.
9. **“`publicLookup` đủ cho metafactory nếu implementation public.”** Sai; metafactory yêu cầu caller lookup full privilege.
10. **“Mỗi function object đều cấp phát một object mới.”** Không có bảo đảm identity tương ứng.
11. **“`invokedynamic` trong nối chuỗi luôn dùng LambdaMetafactory.”** Sai, string concat có bootstrap riêng.
12. **“Metafactory nên thay thế mọi MethodHandles combinator.”** Sai; nó được thiết kế cho protocol tạo lambda/method reference.

## 12. Cách áp dụng trong dự án

Với code Java thường, ưu tiên cú pháp lambda và method reference để compiler suy luận functional interface và generate bootstrap đúng contract. Gọi `metafactory` thủ công hữu ích khi nghiên cứu compiler, runtime dynamic linking hoặc phát hành bytecode đặc biệt.

Nếu đang thiết kế bytecode generator:

- Phát hành **factory/capture descriptor** chính xác, không trộn nó với chữ ký implementation.
- Chọn **direct method/constructor handle** mà caller có quyền truy cập.
- Ghi **SAM erased MethodType** đúng với functional interface và instantiated MethodType phù hợp generic.
- Tính đúng K/N/M, receiver, primitive/reference conversions và return policy.
- Test cả ba giai đoạn: liên kết, capture, invoke; kiểm thử generic/raw misuse và exception propagation.
- Không đưa một pipeline `filterArguments`/`guardWithTest` trực tiếp vào metafactory làm implementation. Nếu cần, viết direct helper method với chữ ký phù hợp hoặc dùng MethodHandle API khác.

Một protocol không tương thích ở runtime không nên được vá bằng quyền Reflection rộng hơn hay `--add-opens` thiếu kiểm soát. Lỗi directness, type arity và accessibility là **những vấn đề khác nhau**; phải xác định đúng nguyên nhân.

## 13. Bài tập

1. Với implementation `(Config,String,int)boolean`, muốn factory capture Config và SAM `(String,int)boolean`. Xác định `K,N,M` và factoryType hợp lệ.
2. Với `findVirtual(Formatter.class,"format",MethodType.methodType(String.class,String.class))`, tính MethodType thực của direct handle. Nếu capture receiver, factory type phải là gì?
3. Tại sao `insertArguments(join,0,"x:")` và direct `upper(String)String` có thể cùng type nhưng chỉ cái direct được metafactory nhận?
4. Khi SAM erased là `(Object)Object` và instantiated là `(String)String`, điều gì xảy ra nếu raw Function nhận Integer?
5. Nếu `Rt=void` còn `Ra=String`, kết quả implementation được xử lý thế nào? Nếu `Rt=String` nhưng `Ra=void` thì sao?
6. Sửa demo để `factoryType=(Object)TextOp` nhưng implementation captured prefix String. Liệt kê bất biến sai và dự đoán exception.
7. Đọc `javap -v -c` cho `LambdaBytecodeView`: tìm bootstrap LambdaMetafactory, implementation direct handle, và opcode nối chuỗi riêng.
8. Một bytecode generator cần dùng pipeline `guardWithTest` như behavior. Vì sao không được truyền adapter đó trực tiếp làm `implementation`? Đề xuất direct helper hoặc API thay thế.
9. Tạo một direct implementation trả `Number` nhưng instantiated yêu cầu `String`. Kiểm tra xem quy tắc return adaptation/link-time và runtime cast nào thực sự được áp dụng.
10. Giải thích vì sao `LambdaConversionException` (linkage) và `ClassCastException` (invocation) cần xử lý bằng hai loại test khác nhau.

## 14. Ghi nhớ

- `LambdaMetafactory` liên kết **direct MethodHandle** với functional interface.
- `factoryType` mô tả **capture** và trả interface; `interfaceMethodType` mô tả SAM; `implementation.type()` mô tả method đích; `dynamicMethodType` mô tả kiểu thực tế cần enforce.
- **`K+N=M`**; captured prefix types phải **`D_i=A_i` chính xác**.
- SAM/instantiated type có thể khác nhau do **generic erasure**, nhưng phải thỏa subtype/adaptability rules.
- Với instance implementation, receiver là một tham số của direct handle và có thể được capture; captured receiver cần non-null.
- **Linkage, capture, invocation** là ba thời điểm với các loại lỗi khác nhau.
- `CallSite` do metafactory trả có target là **factory tạo function object**, không phải bản thân implementation handle.
- Nối chuỗi và lambda đều có thể dùng `invokedynamic` nhưng sử dụng **bootstrap khác nhau**.

## Tài liệu chính thức

- [Java SE 17 — `LambdaMetafactory` và bảng linkage/adaptation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/LambdaMetafactory.html)
- [Java SE 17 — `MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html)
- [Java SE 17 — `MethodHandle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html)
- [Java SE 17 — `MethodType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html)
- [Java SE 17 — `CallSite`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/CallSite.html)
- [Java SE 17 — `StringConcatFactory`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/StringConcatFactory.html)
- [JVMS 17 `5.4.3.6` — Dynamic call site resolution](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.3.6)
