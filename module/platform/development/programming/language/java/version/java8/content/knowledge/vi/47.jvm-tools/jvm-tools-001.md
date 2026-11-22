# Lambda, invokedynamic và LambdaMetafactory trong Java 8+

## 1. Mục tiêu: từ cú pháp lambda đến cách JVM liên kết lời gọi

Từ Java 8, ta có thể truyền hành vi như một giá trị:

~~~java
Predicate<String> notEmpty = text -> !text.isEmpty();
Function<String, String> trim = String::trim;
~~~

Hai biểu thức trên tạo đối tượng thực thi một **functional interface**. Khi gọi method trừu tượng của interface, phần thân lambda hoặc method được tham chiếu mới chạy.

Để hiểu cách JVM thực hiện điều đó, cần phân biệt ba lớp:

- **Lambda expression / method reference:** cú pháp và ngữ nghĩa ở ngôn ngữ Java.
- **invokedynamic:** instruction trong bytecode JVM, dùng một bootstrap method để liên kết dynamic call site với method handle.
- **LambdaMetafactory:** bootstrap factory trong package **java.lang.invoke**, giúp tạo function object thực thi functional interface dựa trên một MethodHandle.

**Điểm quan trọng:** lambda là tính năng của ngôn ngữ Java; invokedynamic là cơ chế liên kết động của JVM; LambdaMetafactory là một API được thiết kế để hỗ trợ việc đánh giá lambda và method reference. Ba khái niệm liên quan chặt chẽ nhưng không phải cùng một thứ.

Các API này có từ Java 8 và vẫn được tài liệu hóa trong Java SE hiện hành. Bài dùng **javap**, **MethodHandle**, **MethodType**, **CallSite**, **metafactory** và **altMetafactory**; không dựa vào cơ chế legacy.

## 2. Functional interface là kiểu đích của lambda

Một **functional interface** là interface có một function contract trừu tượng duy nhất (single abstract method, thường gọi là SAM). Có thể khai báo bằng **@FunctionalInterface**:

~~~java
@FunctionalInterface
interface Formatter {
    String format(String value);
}
~~~

Lambda phải phù hợp với chữ ký của method này:

~~~java
Formatter upper = value -> value.toUpperCase();
System.out.println(upper.format("java"));
// JAVA
~~~

Kiểu đích **Formatter** cho compiler biết:

- Lambda nhận một tham số kiểu String.
- Lambda trả về String.
- Khi gọi **format**, body được thực thi.

Các interface chuẩn trong **java.util.function** cũng là functional interface:

| Interface | Method trừu tượng | Mục đích |
| --- | --- | --- |
| **Runnable** | run() | Công việc không nhận tham số, không trả kết quả |
| **Supplier<T>** | get() | Cung cấp một giá trị |
| **Consumer<T>** | accept(T) | Nhận một giá trị, không trả kết quả |
| **Predicate<T>** | test(T) | Kiểm tra điều kiện, trả boolean |
| **Function<T,R>** | apply(T) | Chuyển T thành R |
| **UnaryOperator<T>** | apply(T) | Biến đổi T thành T |
| **IntUnaryOperator** | applyAsInt(int) | Biến đổi int thành int |

**@FunctionalInterface** giúp compiler kiểm tra contract; annotation này không tạo cơ chế runtime riêng. Interface vẫn có thể khai báo **default method**, **static method** và các method tương thích với method của Object mà không làm mất tính functional.

**Lambda không có kiểu độc lập như một class cụ thể trong source code.** Nó được kiểm tra theo functional interface target type trong assignment, invocation hoặc cast context.

## 3. Lambda expression: tạo hành vi trước, thực thi body sau

Một lambda có thể viết dưới dạng expression body hoặc block body:

~~~java
Function<Integer, Integer> square = number -> number * number;

Consumer<String> print = value -> {
    System.out.println("Value = " + value);
};
~~~

Việc đánh giá biểu thức lambda tạo ra một object của functional interface đích. **Body không chạy ngay lúc tạo object**; body chạy khi method SAM được gọi.

~~~java
Function<Integer, Integer> square = number -> {
    System.out.println("lambda body runs");
    return number * number;
};

System.out.println("before apply");
System.out.println(square.apply(5));
~~~

Output:

~~~text
before apply
lambda body runs
25
~~~

Đây là khác biệt giữa **đánh giá lambda** và **gọi method của object lambda**. Cơ chế runtime cần tạo/cung cấp function object trước; hành vi bên trong được thực thi khi caller gọi SAM.

**Lambda không phải một thread mới.** Viết một lambda chỉ tạo hành vi có thể gọi; muốn chạy song song vẫn phải giao cho Thread, Executor, CompletableFuture hoặc cơ chế concurrency phù hợp.

## 4. Target typing và overload resolution

Compiler xác định kiểu tham số và kết quả của lambda từ **kiểu functional interface đích**:

~~~java
Predicate<String> valid = text -> text.length() >= 3;
Function<String, Integer> length = text -> text.length();
Consumer<String> output = text -> System.out.println(text);
~~~

Cùng một body **text -> text.length() >= 3** có thể phù hợp Predicate<String>, nhưng không phù hợp Function<String,Integer> vì kết quả là boolean thay vì Integer.

Khi có overload nhận nhiều functional interface có chữ ký gần nhau, lambda có thể khiến lời gọi bị **ambiguous**:

~~~java
static void process(Predicate<String> test) { }
static void process(Function<String, Boolean> test) { }

// Có thể mơ hồ vì lambda phù hợp cả hai function type:
process(text -> text.isEmpty());
~~~

Có thể làm rõ bằng kiểu đích/cast hoặc đổi tên API:

~~~java
process((Predicate<String>) text -> text.isEmpty());
~~~

**Đừng cố đoán kiểu lambda chỉ từ tên tham số.** Xem method overload, generic type và return type. Method reference cũng được type-check theo target type.

## 5. Method reference: một cách viết ngắn của hành vi gọi method

Method reference dùng toán tử **::** và vẫn cần functional interface đích.

Bốn dạng thường gặp:

~~~java
// Static method reference
Function<String, Integer> parse = Integer::parseInt;

// Instance method của một object cụ thể
Function<String, String> trim = String::trim;

// Instance method qua một đối tượng được truyền vào
BiFunction<String, String, String> replace =
        String::replace;

// Constructor reference
Supplier<StringBuilder> builder = StringBuilder::new;
~~~

Ở ví dụ **String::trim**, đối tượng String được truyền vào làm receiver khi method trim() được gọi. Với **service::handle**, receiver service đã được chỉ định trong biểu thức method reference.

Method reference không phải một loại function object khác lambda; nó cũng được chuyển thành object của functional interface target type. **Javac thường dùng invokedynamic và LambdaMetafactory cho cả lambda lẫn method reference**.

Chọn cách viết theo độ rõ: nếu chỉ tham chiếu một method có chữ ký phù hợp, method reference thường gọn; nếu cần thêm validation, logging hoặc chuyển đổi, lambda body dễ đọc hơn.

## 6. Capturing và non-capturing lambda

**Non-capturing lambda** không sử dụng biến bên ngoài:

~~~java
Runnable task = () -> System.out.println("ready");
~~~

**Capturing lambda** sử dụng một hoặc nhiều giá trị từ scope bên ngoài:

~~~java
int factor = 3;
IntUnaryOperator multiply = value -> value * factor;
System.out.println(multiply.applyAsInt(7));
// 21
~~~

Ở ví dụ thứ hai, **factor** là giá trị cần capture. JVM cần cung cấp giá trị này cho function object để khi gọi applyAsInt, phần thân có thể tính đúng.

Về khái niệm, lambda có thể xem như function object được tạo từ:

- Method handle mô tả phần implementation.
- Các capture arguments, nếu có.
- Các argument được truyền vào method SAM mỗi lần invocation.

**Không có capture** thì factory không cần nhận capture argument. Có capture thì factory target có các tham số tương ứng, và việc đánh giá lambda cung cấp các giá trị đó.

Không nên giả định non-capturing lambda luôn là singleton hay capturing lambda luôn tạo một object mới ở mỗi lần đánh giá; identity và allocation là chi tiết implementation không được đảm bảo theo cách đó.

## 7. Quy tắc effectively final khi capture local variable

Local variable được tham chiếu trong lambda phải là **final hoặc effectively final**:

~~~java
int base = 10;
IntUnaryOperator addBase = value -> value + base; // Hợp lệ
~~~

Ví dụ sau không hợp lệ:

~~~java
int base = 10;
IntUnaryOperator addBase = value -> value + base;
base++; // Compile error: base không còn effectively final
~~~

Lý do: lambda capture giá trị local theo quy tắc ngôn ngữ, không tạo một liên kết cho phép lambda sửa local variable sau này.

Nếu capture một object reference:

~~~java
List<String> names = new ArrayList<>();
Runnable addName = () -> names.add("Ada");
addName.run();
System.out.println(names);
~~~

Biến **names** không bị gán lại, nên effectively final. **Object mà nó tham chiếu vẫn có thể mutable**; quy tắc effectively final không làm object trở thành immutable và không tự tạo thread safety.

Nếu nhiều thread cùng sửa object được capture, vẫn cần đồng bộ, concurrent collection hoặc một thiết kế quản lý state thích hợp.

## 8. this trong lambda khác anonymous class

Trong lambda, **this** có nghĩa là **this của scope bao quanh**, không phải một instance mới đại diện cho lambda:

~~~java
class Service {
    private final String name = "billing";

    Runnable task() {
        return () -> System.out.println(this.name);
    }
}
~~~

Trong lambda trên, this là đối tượng Service.

Anonymous class có ngữ nghĩa khác:

~~~java
Runnable task = new Runnable() {
    @Override
    public void run() {
        System.out.println(this.toString());
    }
};
~~~

Ở anonymous class, this tham chiếu instance anonymous class. Đây là một khác biệt quan trọng khi chuyển code từ anonymous class sang lambda.

Lambda cũng không khai báo constructor hoặc instance field như một class thông thường. Nếu cần một object có state/method lifecycle phức tạp, class cụ thể có thể diễn đạt ý định rõ hơn.

## 9. invokedynamic là instruction liên kết động của JVM

**invokedynamic** là một JVM bytecode instruction được thêm từ Java 7. Nó cho phép một call site được liên kết bằng **bootstrap method**, thay vì chỉ chọn đích theo cách gọi method tĩnh/virtual thông thường.

Ở Java 8, javac dùng invokedynamic để hỗ trợ lambda expression và method reference.

Có thể hiểu luồng tổng quát:

~~~text
Java source:
    Function<String, String> f = String::trim;
                  |
                  v
Compiler tạo class file:
    CONSTANT_InvokeDynamic
    BootstrapMethods
    MethodHandle / MethodType / static arguments
                  |
                  v
JVM resolve dynamic call site:
    gọi bootstrap method
                  |
                  v
CallSite + target MethodHandle
                  |
                  v
Tạo/capture function object
                  |
                  v
Gọi method SAM khi ứng dụng sử dụng object
~~~

**invokedynamic không phải một API Java mà ta gọi trực tiếp như một method thông thường.** Đây là instruction trong bytecode; source Java dùng lambda/method reference, còn compiler và JVM tạo/liên kết call site.

Cũng không nên đồng nhất invokedynamic với reflection. Nó là cơ chế dynamic linkage ở cấp JVM, có type descriptor và bootstrap protocol riêng.

## 10. Dynamic call site và bootstrap method

Mỗi vị trí **invokedynamic** trong bytecode là một **dynamic call site** cụ thể. Trong class file, thông tin call site được liên kết với:

- Một tên invocation.
- Một MethodType mô tả chữ ký call site.
- Một bootstrap method handle.
- Các static bootstrap arguments trong class-file metadata.

Khi JVM resolve call site, bootstrap method được gọi để trả về một **CallSite**. CallSite có target MethodHandle với kiểu tương thích descriptor của dynamic call site.

Sau khi call site được liên kết, những lần thực thi tiếp theo đi qua target đã được liên kết. Bootstrap không phải một lời gọi được thực hiện lại như phần thân lambda ở mỗi lần gọi SAM.

**Phân biệt ba thời điểm:**

1. **Linkage:** JVM resolve call site và gọi bootstrap method.
2. **Capture:** target của call site được gọi để tạo/cung cấp function object, kèm capture values nếu có.
3. **Invocation:** ứng dụng gọi method SAM trên function object; implementation method được thực thi.

Một bootstrap site có thể được dùng nhiều lần để capture các function object. Một function object sau khi được tạo cũng có thể nhận nhiều lần invocation.

## 11. BootstrapMethods và constant pool trong class file

Class file có thể chứa constant pool entry **CONSTANT_InvokeDynamic** và một attribute tên **BootstrapMethods**.

BootstrapMethods lưu:

- Method handle của bootstrap method.
- Danh sách static arguments truyền cho bootstrap.
- Thông tin để JVM resolve dynamic call site.

Với lambda, static arguments thường mô tả method type của SAM, implementation method handle và dynamic method type cần áp dụng.

Trong output của **javap -v**, ta thường thấy các mục:

~~~text
InvokeDynamic
BootstrapMethods
REF_invokeStatic java/lang/invoke/LambdaMetafactory.metafactory
REF_invokeStatic java/lang/invoke/LambdaMetafactory.altMetafactory
~~~

Tên **lambda$...** đôi khi xuất hiện như method implementation tổng hợp do compiler tạo cho lambda body. Tên và cách bố trí cụ thể có thể khác giữa compiler/version.

**Đừng viết code production phụ thuộc vào tên synthetic method, constant-pool index hoặc tên class runtime của lambda.** Chúng là chi tiết compiler/VM.

## 12. LambdaMetafactory làm gì?

**java.lang.invoke.LambdaMetafactory** là một class final cung cấp các phương thức hỗ trợ tạo function object thực thi một hoặc nhiều interface bằng cách ủy quyền tới một **MethodHandle**.

Các phương thức chính:

~~~java
LambdaMetafactory.metafactory(...)
LambdaMetafactory.altMetafactory(...)
~~~

**metafactory** là phiên bản tiêu chuẩn, gọn hơn. **altMetafactory** mở rộng khả năng cấu hình, ví dụ:

- Function object có thể implement thêm marker interfaces.
- Có thể tạo thêm bridge method signatures.
- Có thể yêu cầu function object Serializable.

Javadoc mô tả ba giai đoạn **linkage, capture và invocation**. CallSite trả về hoạt động như một factory tạo function objects; implementation method được tham chiếu bằng MethodHandle.

**API có từ Java 8 (Since 1.8)** và được thiết kế để hỗ trợ việc đánh giá lambda expression/method reference trong ngôn ngữ Java.

## 13. Sáu tham số của metafactory

Chữ ký chuẩn:

~~~java
public static CallSite metafactory(
        MethodHandles.Lookup caller,
        String interfaceMethodName,
        MethodType factoryType,
        MethodType interfaceMethodType,
        MethodHandle implementation,
        MethodType dynamicMethodType)
        throws LambdaConversionException;
~~~

Ý nghĩa:

| Tham số | Ý nghĩa |
| --- | --- |
| **caller** | Lookup context và quyền truy cập của class caller |
| **interfaceMethodName** | Tên method SAM cần implement |
| **factoryType** | Chữ ký target của CallSite; tham số là capture variables, return type là interface đích |
| **interfaceMethodType** | Chữ ký method SAM của interface |
| **implementation** | Direct MethodHandle tới method/constructor thực hiện logic |
| **dynamicMethodType** | Chữ ký được kiểm tra khi invocation; thường giống interfaceMethodType trong trường hợp đơn giản |

Điểm dễ nhầm là **factoryType không phải chữ ký SAM**. FactoryType mô tả việc tạo object; interfaceMethodType mô tả method được gọi trên object.

Implementation handle có thể nhận thêm tham số capture. Những tham số này được đưa vào factory target trước các argument của SAM method khi implementation được gọi.

Nếu kiểu tham số/return không đáp ứng các quy tắc adaptation của LambdaMetafactory, linkage có thể thất bại với **LambdaConversionException**.

## 14. MethodHandle, MethodType và CallSite

Ba kiểu quan trọng của package **java.lang.invoke**:

**MethodHandle** là một tham chiếu có kiểu tới hành vi có thể gọi. Nó có thể tham chiếu static method, instance method, constructor hoặc một số dạng invocation khác.

**MethodType** mô tả chính xác danh sách kiểu tham số và kiểu trả về của một method handle/call site.

**CallSite** giữ target MethodHandle được liên kết với một dynamic call site. Target của nó có kiểu phải tương thích với descriptor mà JVM yêu cầu.

Ví dụ tạo MethodHandle tới static method:

~~~java
MethodHandles.Lookup lookup = MethodHandles.lookup();
MethodHandle handle = lookup.findStatic(
        Calculator.class,
        "add",
        MethodType.methodType(int.class, int.class, int.class));
~~~

Đoạn trên cần class Calculator có method **static int add(int a, int b)**. Nó là snippet minh họa, không phải chương trình độc lập.

**MethodHandle có type checking riêng.** Dùng invokeExact đòi hỏi kiểu invocation chính xác; nếu kiểu compile-time không khớp với MethodHandle type, có thể nhận **WrongMethodTypeException**. invoke cho phép một số adaptation rộng hơn.

## 15. Hiểu factoryType bằng ví dụ capture

Giả sử functional interface:

~~~java
@FunctionalInterface
interface Formatter {
    String format(String value);
}
~~~

Implementation method cần một prefix đã capture và một value từ SAM:

~~~java
static String addPrefix(String prefix, String value) {
    return prefix + value;
}
~~~

Các chữ ký có dạng:

~~~text
factoryType:
    (String capturedPrefix) -> Formatter

interfaceMethodType:
    (String value) -> String

implementation:
    (String prefix, String value) -> String

dynamicMethodType:
    (String value) -> String
~~~

Khi factory target nhận **"Hello, "**, nó tạo một Formatter đã capture prefix đó. Khi caller gọi **formatter.format("JVM")**, implementation nhận hai đối số theo thứ tự **prefix đã capture** rồi **value từ SAM**.

Đây là lý do implementation method có thể có nhiều tham số hơn method SAM. Capture arguments là một phần của factory signature, không phải tham số mà caller phải truyền mỗi lần gọi format.

## 16. altMetafactory: bridge methods, marker interfaces và Serializable

**altMetafactory** là phiên bản tổng quát hơn của metafactory. Nó nhận một mảng Object arguments với các metadata bổ sung và flags.

Ba flag đáng chú ý:

| Flag | Công dụng |
| --- | --- |
| **FLAG_BRIDGES** | Yêu cầu thêm method signatures cần bridge tới implementation |
| **FLAG_MARKERS** | Yêu cầu function object implement thêm các interface khác |
| **FLAG_SERIALIZABLE** | Yêu cầu function object có khả năng Serializable |

Ví dụ lambda target là giao của Runnable và Serializable:

~~~java
Runnable task = (Runnable & Serializable) () -> {
    System.out.println("run");
};
~~~

Javac có thể dùng **altMetafactory** để tạo object implement cả Runnable lẫn Serializable. Trong output javap -v, ta có thể thấy bootstrap method trỏ tới LambdaMetafactory.altMetafactory.

**Không nên serialize lambda như một định dạng dữ liệu bền vững của ứng dụng.** Serializable lambda dùng **SerializedLambda** và cần hỗ trợ **$deserializeLambda$** trong capturing class. Thay đổi tên class, method hoặc cấu trúc implementation có thể ảnh hưởng khả năng deserialize; nếu cần lưu trữ lâu dài, hãy định nghĩa DTO/schema/version rõ ràng.

## 17. Chương trình Java chạy được: lambda, method reference và metafactory

Tạo tệp **LambdaInvokeDynamicDemo.java**. Chương trình dùng cú pháp Java 8 và có thể biên dịch trên JDK 8 trở lên. Phần gọi LambdaMetafactory trực tiếp được giữ trong ví dụ để học cách các tham số linkage liên hệ với nhau; **ứng dụng thông thường nên viết lambda/method reference và để compiler tạo bootstrap call site**.

~~~java
import java.io.Serializable;
import java.lang.invoke.CallSite;
import java.lang.invoke.LambdaMetafactory;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.util.function.Function;
import java.util.function.IntUnaryOperator;

public class LambdaInvokeDynamicDemo {
    @FunctionalInterface
    public interface Formatter {
        String format(String value);
    }

    private static String addPrefix(String prefix, String value) {
        return prefix + value;
    }

    private static Formatter createWithMetafactory(String prefix)
            throws Throwable {
        MethodHandles.Lookup caller = MethodHandles.lookup();
        MethodHandle implementation = caller.findStatic(
                LambdaInvokeDynamicDemo.class,
                "addPrefix",
                MethodType.methodType(
                        String.class, String.class, String.class));

        CallSite factory = LambdaMetafactory.metafactory(
                caller,
                "format",
                MethodType.methodType(Formatter.class, String.class),
                MethodType.methodType(String.class, String.class),
                implementation,
                MethodType.methodType(String.class, String.class));

        return (Formatter) factory.getTarget().invokeExact(prefix);
    }

    public static void main(String[] args) throws Throwable {
        int factor = 3;
        IntUnaryOperator multiply = value -> value * factor;
        Function<String, String> trim = String::trim;
        Formatter formatter = createWithMetafactory("Hello, ");

        Runnable serializableLambda =
                (Runnable & Serializable) () -> { };

        System.out.println("capturing lambda: " +
                multiply.applyAsInt(7));
        System.out.println("method reference: [" +
                trim.apply("  Java  ") + "]");
        System.out.println("manual metafactory demo: " +
                formatter.format("JVM"));
        System.out.println("serializable intersection: " +
                (serializableLambda instanceof Serializable));
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac --release 17 LambdaInvokeDynamicDemo.java
java LambdaInvokeDynamicDemo
~~~

**Stdout đã kiểm chứng:**

~~~text
capturing lambda: 21
method reference: [Java]
manual metafactory demo: Hello, JVM
serializable intersection: true
~~~

Có thể biên dịch cùng source ở target Java 8 bằng JDK mới:

~~~bash
javac -Xlint:-options --release 8 LambdaInvokeDynamicDemo.java
java -cp . LambdaInvokeDynamicDemo
~~~

Trên JDK 8 thật, dùng **javac LambdaInvokeDynamicDemo.java** và **java LambdaInvokeDynamicDemo**; tùy chọn --release được bổ sung ở JDK sau.

**Giải thích phần direct metafactory:**

- **lookup.findStatic(...)** tạo direct MethodHandle tới addPrefix(String,String).
- **factoryType** là (String)Formatter, vì prefix là capture argument.
- **interfaceMethodType** là (String)String, đúng chữ ký Formatter.format.
- Implementation handle có hai String: prefix được capture và value từ invocation.
- **factory.getTarget()** là MethodHandle tạo Formatter; invokeExact(prefix) thực hiện capture.

**Giới hạn:** direct invocation của LambdaMetafactory ở đây là lab để hiểu linkage. Javadoc cảnh báo các mục đích sử dụng ngoài việc evaluate lambda/method reference trong ngôn ngữ Java là ngoài mục đích thiết kế và hành vi không được bảo đảm như một API factory tổng quát.

## 18. Dùng javap để xem invokedynamic trong class file

Sau khi biên dịch, chạy:

~~~bash
javap -classpath . -c -v -p LambdaInvokeDynamicDemo
~~~

Các tùy chọn:

- **-c:** hiển thị bytecode của từng method.
- **-v:** hiển thị constant pool, bootstrap methods và metadata chi tiết.
- **-p:** hiển thị cả private members.

Với JDK compiler đã kiểm thử ở target Java 8, các phần quan trọng có dạng:

~~~text
major version: 52

InvokeDynamic #0:applyAsInt:(I)Ljava/util/function/IntUnaryOperator;
InvokeDynamic #1:apply:()Ljava/util/function/Function;
InvokeDynamic #2:run:()Ljava/lang/Runnable;

BootstrapMethods:
  REF_invokeStatic java/lang/invoke/LambdaMetafactory.metafactory
  REF_invokeStatic java/lang/invoke/LambdaMetafactory.metafactory
  REF_invokeStatic java/lang/invoke/LambdaMetafactory.altMetafactory
~~~

**Major version 52** là class file Java 8. Ba call site minh họa:

- **applyAsInt:(I)IntUnaryOperator:** factory nhận một int capture (factor).
- **apply:()Function:** method reference String::trim không cần capture argument.
- **run:()Runnable:** lambda target giao với Serializable; compiler dùng altMetafactory.

BootstrapMethods cũng chứa implementation MethodHandle. Với capturing lambda, output đã kiểm thử hiển thị method tổng hợp dạng **lambda$main$0:(II)I**, nhận factor đã capture và input của applyAsInt.

**Chỉ xem đây là output đại diện.** Constant-pool index, tên synthetic method và bố cục class file có thể thay đổi giữa phiên bản javac. Không hard-code những tên này vào ứng dụng.

## 19. Tại sao lambda identity không được bảo đảm?

JLS cho phép runtime **tạo object mới hoặc tái sử dụng object có sẵn** khi đánh giá lambda. Identity của kết quả là không dự đoán được giữa implementation hoặc giữa các lần đánh giá.

Vì vậy, không viết logic dựa trên:

~~~java
Runnable first = () -> System.out.println("x");
Runnable second = () -> System.out.println("x");

boolean same = first == second; // Không có contract identity để dựa vào.
~~~

Cũng không nên:

- Dùng lambda làm monitor trong synchronized.
- Dùng System.identityHashCode(lambda) làm ID bền vững.
- Dựa vào lambda.getClass().getName() để nhận diện loại logic.
- Dựa vào toString() của lambda để ghi format dữ liệu.

Nếu cần identity ổn định, tạo một object/key rõ ràng trong domain. Nếu cần cache function, thiết kế cache theo key và lifecycle riêng thay vì dựa vào identity runtime của lambda.

## 20. Capturing có đồng nghĩa luôn cấp phát object mới?

Không. JLS và LambdaMetafactory cho phép implementation lựa chọn object mới hoặc instance có sẵn. Trong một số tình huống, non-capturing lambda có thể được tái sử dụng. Với capturing lambda, factory nhận capture arguments; runtime có thể tối ưu theo cách implementation cho phép.

**Không được suy ra các quy tắc sau:**

- Mỗi lambda expression luôn tạo một class mới.
- Mỗi lần đi qua một dòng lambda luôn cấp phát một object mới.
- Non-capturing lambda chắc chắn là singleton.
- Capturing lambda luôn cấp phát đúng một object theo mỗi lần gọi.
- invokedynamic tự động làm code nhanh hơn mọi anonymous class.

JIT có thể inline hoặc tối ưu một số trường hợp, nhưng hiệu năng phụ thuộc workload, JVM, escape analysis, allocation và call pattern. Nếu hiệu năng là yêu cầu thực, đo bằng benchmark phù hợp (ví dụ JMH) thay vì đoán từ cú pháp.

## 21. Lambda, anonymous class và method reference khác nhau thế nào?

| Khía cạnh | Lambda | Anonymous class | Method reference |
| --- | --- | --- | --- |
| Mục đích | Định nghĩa hành vi SAM ngắn gọn | Tạo class instance không đặt tên, có thể thêm state/method | Tham chiếu method/constructor có sẵn |
| Target | Functional interface | Class hoặc interface | Functional interface |
| this | this của scope ngoài | this của anonymous object | Theo receiver được tham chiếu |
| Field riêng | Không khai báo như class | Có thể khai báo field | Không |
| Runtime implementation | Compiler/JVM linh hoạt | Class anonymous trong class file | Thường cùng cơ chế lambda linkage |
| Khi phù hợp | Hành vi nhỏ, truyền callback | Cần state/object behavior riêng | Method đã có đúng logic |

Không phải mọi anonymous class đều nên chuyển thành lambda. Nếu anonymous class dùng nhiều field, override nhiều method, cần this riêng hoặc có cấu trúc object rõ, class cụ thể có thể dễ hiểu và dễ bảo trì hơn.

Method reference phù hợp khi body chỉ chuyển tiếp tới một method đã có. Nếu cần thêm validation, logging hoặc chuyển đổi, lambda thường biểu đạt tốt hơn.

## 22. Bridge method và generic functional interface

Một functional interface generic có thể bị **type erasure** khi biên dịch:

~~~java
Function<String, Integer> parseLength = text -> text.length();
~~~

Ở source, apply được nhìn như nhận String và trả Integer. Ở bytecode sau erasure, signature tổng quát của Function sử dụng Object. Compiler/runtime phải bảo đảm việc cast và adaptation đúng với type đã chọn.

**LambdaMetafactory.altMetafactory** hỗ trợ FLAG_BRIDGES để yêu cầu thêm method signatures cần thiết cho bridge/adaptation khi một function object phải implement nhiều VM method signatures tương ứng với một method logic.

**Không tự viết bridge method chỉ vì nhìn thấy nó trong javap.** Bridge là cơ chế tương thích chữ ký, thường do compiler/runtime tạo để giữ ngữ nghĩa generic/erasure. Đọc source contract và target functional interface trước khi kết luận.

## 23. Exceptions và lỗi linkage thường gặp

Một số lỗi có thể xuất hiện ở các giai đoạn khác nhau:

| Lỗi | Thời điểm thường gặp | Nguyên nhân |
| --- | --- | --- |
| **IllegalAccessException** | Tìm MethodHandle | Lookup không có quyền truy cập method/constructor |
| **LambdaConversionException** | Gọi metafactory trực tiếp | Factory/SAM/implementation MethodType không thỏa linkage invariants |
| **WrongMethodTypeException** | Gọi MethodHandle | Kiểu compile-time của invokeExact không khớp method handle type |
| **ClassCastException** | Invocation/adaptation | Giá trị runtime không phù hợp kiểu được yêu cầu |
| **BootstrapMethodError** | JVM resolve invokedynamic | Bootstrap method lỗi, không trả CallSite phù hợp hoặc linkage thất bại |
| **NullPointerException** | Khi thực thi lambda body hoặc dereference capture | Đối tượng capture/reference null |

**BootstrapMethodError không phải lỗi nghiệp vụ thông thường của lambda body.** Nó báo lỗi liên kết bootstrap call site. Khi xảy ra, kiểm tra cause để tìm lỗi gốc như LambdaConversionException hoặc WrongMethodTypeException.

Lambda body cũng tuân theo checked exception rules của functional interface. Ví dụ **Runnable.run()** không khai báo checked exception; **Callable.call()** khai báo throws Exception. Nếu method được tham chiếu ném checked exception không phù hợp SAM target, compiler sẽ báo lỗi hoặc yêu cầu wrapper/functional interface có throws tương ứng.

Không dùng catch(Throwable) để che mọi lỗi lambda trong ứng dụng. Chỉ catch loại lỗi mà tầng đó có thể xử lý hợp lý; lỗi linkage thường cần sửa code/compiler/provider/configuration.

## 24. Serialization của lambda: chỉ bật khi có nhu cầu rõ ràng

Lambda **không Serializable mặc định** chỉ vì nó implement một functional interface. Có thể chọn target intersection:

~~~java
Runnable task = (Runnable & Serializable) () -> work();
~~~

Khi target interface là Serializable (hoặc intersection type chứa Serializable), object lambda có thể được tạo dưới dạng serializable. Compiler có thể dùng **altMetafactory** và flag tương ứng.

Cơ chế serialization dùng **SerializedLambda** và capturing class cần method hỗ trợ **$deserializeLambda$**. Captured values cũng phải phù hợp với quá trình serialize.

**Không dùng serialized lambda làm định dạng lưu trữ hoặc giao tiếp lâu dài giữa các phiên bản ứng dụng** nếu không có một compatibility contract rõ ràng. Đổi tên method, class, capture structure hoặc compiler output có thể ảnh hưởng deserialization.

Nếu cần lưu một tác vụ hoặc callback, hãy lưu **mã định danh tác vụ + tham số DTO + version schema**, rồi ánh xạ sang implementation bằng registry ở runtime. Đó là một contract bền vững hơn phụ thuộc chi tiết lambda implementation.

## 25. Lỗi thường gặp và cách kiểm tra

1. **Nghĩ lambda là một method độc lập.** Nó là biểu thức tạo object của functional interface.
2. **Nghĩ body chạy ngay khi gán lambda.** Body chạy khi gọi SAM method.
3. **Không xác định target type.** Lambda cần functional interface target type trong assignment/invocation/cast context.
4. **Interface có nhiều abstract methods.** Không còn là SAM target phù hợp, trừ các method được tính theo quy tắc functional interface.
5. **Capture local variable rồi gán lại.** Local phải final/effectively final.
6. **Nghĩ effectively final làm object immutable.** Nó chỉ giới hạn việc gán lại biến, không khóa state của object.
7. **Dùng this như thể lambda có instance riêng.** Lambda dùng this lexical của scope ngoài.
8. **Nghĩ invokedynamic gọi trực tiếp lambda body.** Call site thường tạo/capture function object; SAM invocation mới gọi implementation.
9. **Nghĩ bootstrap method chạy ở mọi lần gọi SAM.** Bootstrap xử lý linkage của call site; target được dùng sau khi liên kết.
10. **Nghĩ mọi lambda luôn sinh class file riêng.** Implementation class/object là chi tiết runtime.
11. **Nghĩ non-capturing lambda luôn singleton.** Không có identity guarantee.
12. **So sánh lambda bằng ==.** JLS không bảo đảm identity.
13. **Dùng lambda làm monitor.** Identity không ổn định giữa implementation/evaluation.
14. **Nghĩ invokedynamic chỉ dùng cho lambda.** Nó là cơ chế dynamic linkage tổng quát của JVM.
15. **Nghĩ mọi compiler buộc phải tạo đúng cùng bytecode.** JLS cho implementation flexibility; javap output phụ thuộc compiler.
16. **Nhầm factoryType với SAM MethodType.** FactoryType chứa capture parameters và trả functional interface.
17. **Truyền MethodHandle sai kiểu vào metafactory.** Linkage invariants có thể thất bại.
18. **Gọi invokeExact với kiểu không chính xác.** Có thể nhận WrongMethodTypeException.
19. **Dùng direct LambdaMetafactory như một API tạo callback tổng quát.** Javadoc nói các use ngoài việc evaluate lambda/method reference là ngoài mục đích thiết kế.
20. **Dựa vào tên lambda$... hoặc hidden implementation class.** Đây là chi tiết compiler/runtime.
21. **Bật Serializable cho mọi lambda.** Serialization có overhead, security và compatibility implications.
22. **Coi tag serializable đảm bảo captured object serialize được.** Capture values cũng cần thỏa điều kiện.
23. **Nghĩ lambda tự tạo thread.** Nó chỉ mô tả hành vi; executor/thread mới quyết định execution.
24. **Nghĩ capture mutable object tự thread-safe.** Cần concurrency control riêng.
25. **Tối ưu hiệu năng theo cảm tính.** Đo workload thật bằng benchmark thích hợp.

## 26. Checklist học và debug bằng công cụ

Khi cần hiểu một lambda cụ thể, đi theo thứ tự:

1. Xác định **functional interface target type** và method SAM.
2. Ghi lại input/output type của SAM.
3. Xác định lambda có **capture** biến nào.
4. Kiểm tra local captures có effectively final không.
5. Compile với target JDK mong muốn.
6. Dùng **javap -c -v -p** xem invokedynamic, constant pool và BootstrapMethods.
7. Tìm bootstrap method: LambdaMetafactory.metafactory hay altMetafactory.
8. Xem static arguments để xác định SAM MethodType, implementation MethodHandle và dynamic MethodType.
9. Xác định factory signature có capture parameters nào.
10. Chỉ dùng class/method synthetic trong output làm manh mối debug, không làm API contract.
11. Nếu có lỗi linkage, đọc BootstrapMethodError cause.
12. Nếu có lỗi invocation, kiểm tra MethodType, access và adaptation.
13. Nếu có vấn đề performance, benchmark cả baseline và implementation thực tế.
14. Nếu có serialization, xác minh SerializedLambda/captured values và compatibility của phiên bản.

**Các lệnh mẫu:**

~~~bash
javac --release 17 -d out LambdaInvokeDynamicDemo.java
java -cp out LambdaInvokeDynamicDemo
javap -classpath out -c -v -p LambdaInvokeDynamicDemo
~~~

Với target Java 8, dùng **javac --release 8** trên JDK mới hoặc javac trực tiếp trên JDK 8. Class file Java 8 có major version **52**; class file phải được chạy trên JVM hỗ trợ phiên bản tương ứng.

## 27. Bài tập có đáp án

**1.** Lambda x -> x * 2 cần kiểu gì để compiler biết x là int?  
**Đáp án:** Một target functional interface như IntUnaryOperator hoặc một cast/assignment có type tương ứng.

**2.** Body lambda chạy ở thời điểm gán biến hay lúc gọi SAM?  
**Đáp án:** Khi gọi method SAM; đánh giá lambda tạo/cung cấp function object.

**3.** Runnable r = () -> work() có tự tạo thread không?  
**Đáp án:** Không. Nó chỉ là một Runnable object; phải giao cho Thread/Executor nếu muốn chạy trên thread.

**4.** Vì sao int factor=2; lambda x -> x*factor hợp lệ?  
**Đáp án:** factor effectively final.

**5.** Có thể gán lại factor sau khi lambda capture không?  
**Đáp án:** Không, compiler báo lỗi vì factor không còn effectively final.

**6.** Trong lambda của instance method, this là ai?  
**Đáp án:** this của enclosing instance, không phải object riêng của lambda.

**7.** invokedynamic được thêm từ Java nào?  
**Đáp án:** Java 7; Java 8 dùng nó để hỗ trợ lambda/method reference trong javac.

**8.** LambdaMetafactory có từ phiên bản nào?  
**Đáp án:** Java 8 (Since 1.8).

**9.** Bootstrap method trả về kiểu gì?  
**Đáp án:** CallSite hoặc subtype của CallSite theo JVM linkage contract.

**10.** factoryType mô tả gì?  
**Đáp án:** Chữ ký factory target, trong đó tham số là capture values và return type là functional interface.

**11.** interfaceMethodType mô tả gì?  
**Đáp án:** Chữ ký SAM method cần implement.

**12.** implementation của metafactory là gì?  
**Đáp án:** Direct MethodHandle tới method/constructor chứa implementation behavior.

**13.** Capture values được truyền lúc nào?  
**Đáp án:** Khi target factory của CallSite được gọi để tạo/capture function object.

**14.** Khi nào lambda body được thực thi?  
**Đáp án:** Khi method SAM của function object được gọi.

**15.** altMetafactory hỗ trợ thêm gì?  
**Đáp án:** Bridge method signatures, marker interfaces và Serializable qua flags.

**16.** Vì sao không dùng lambda1 == lambda2 để xác định cùng logic?  
**Đáp án:** Identity lambda không được JLS bảo đảm; runtime có thể tạo mới hoặc tái sử dụng instance.

**17.** javap -v giúp tìm thông tin nào?  
**Đáp án:** Constant pool, InvokeDynamic entries, BootstrapMethods, method handles và method types.

**18.** Một BootstrapMethodError xảy ra có thể chỉ ra điều gì?  
**Đáp án:** Bootstrap method hoặc linkage của dynamic call site thất bại; đọc cause để tìm lỗi gốc.

**19.** Có nên tự gọi LambdaMetafactory trong mọi ứng dụng để tạo callback?  
**Đáp án:** Không. API được thiết kế chủ yếu làm bootstrap cho lambda/method reference; source lambda thông thường dễ đọc và được compiler xử lý.

**20.** Serializable lambda có phù hợp làm protocol lưu trữ lâu dài không?  
**Đáp án:** Không nên; dùng DTO/schema/version tường minh.

## 28. Tài liệu chính thức Java hiện hành

- **LambdaMetafactory (Java SE 26):** mô tả linkage/capture/invocation, metafactory, altMetafactory, flags, type invariants và API note: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/LambdaMetafactory.html
- **MethodHandle (Java SE 26):** invocation, invokeExact, adaptation và method handle types: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandle.html
- **MethodHandles.Lookup (Java SE 26):** lookup context, access privileges và findStatic/findVirtual: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html
- **MethodType (Java SE 26):** mô tả kiểu tham số/return của method handle và call site: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodType.html
- **CallSite (Java SE 26):** dynamic call site target và các dạng CallSite: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/CallSite.html
- **Java Language Specification, §9.8:** functional interface: https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-9.html
- **Java Language Specification, §15.27:** lambda parameters, body, target typing và runtime evaluation/identity: https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-15.html
- **Java Virtual Machine Specification, §6.5 invokedynamic:** dynamic call site và bootstrap resolution: https://docs.oracle.com/javase/specs/jvms/se27/html/jvms-6.html
- **Java Virtual Machine Specification, §4.7.23 BootstrapMethods:** class-file attribute lưu bootstrap methods và static arguments: https://docs.oracle.com/javase/specs/jvms/se26/html/jvms-4.html
- **Oracle Java 8 VM Guide — Support for Non-Java Languages:** mô tả bootstrap method, CallSite và invokedynamic: https://docs.oracle.com/javase/8/docs/technotes/guides/vm/multiple-language-support.html

**Mức kiểm chứng của ví dụ:** LambdaInvokeDynamicDemo.java đã được biên dịch và chạy bằng target Java 17 và target Java 8. Output của cả hai lần chạy giống nhau. javap -v -p trên class file major version 52 xác nhận invokedynamic sites cho capturing lambda, method reference và serializable intersection; BootstrapMethods trỏ tới metafactory và altMetafactory. Tên synthetic method và constant-pool index là output của compiler kiểm thử, không phải cam kết cho mọi JDK.

**Kết luận:** source lambda biểu diễn hành vi qua functional interface; javac dùng invokedynamic để tạo dynamic call site; LambdaMetafactory liên kết call site với MethodHandle và tạo function object. Hiểu riêng **linkage, capture, invocation** sẽ giúp đọc bytecode, debug lỗi MethodType/BootstrapMethodError và tránh phụ thuộc vào chi tiết runtime không được Java bảo đảm.
