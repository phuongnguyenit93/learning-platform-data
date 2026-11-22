# Quan sát lambda và method reference trong bytecode Java

## 1. Mục tiêu quan sát: cú pháp ngắn gọn được biên dịch thành gì?

Lambda và method reference là hai cách tạo giá trị của **functional interface** (giao diện có đúng một abstract method theo quy tắc functional interface). Ví dụ, cả `x -> x + 1` và `SomeType::someMethod` có thể cung cấp implementation cho một mục tiêu có dạng Single Abstract Method (SAM). Tuy nhiên, mã nguồn trông giống một anonymous class không có nghĩa `javac` luôn sinh một file `SomeClass$1.class` cho từng lambda.

Với `javac` hiện đại trên Java 17+, cách biên dịch thông dụng là:

1. Compiler xác định *target type* của lambda/method reference và chữ ký SAM.
2. Nó tạo một **`invokedynamic` call site** để tạo/lấy instance của functional interface khi biểu thức được đánh giá.
3. Call site tham chiếu một **bootstrap method** trong `java.lang.invoke.LambdaMetafactory` (thường `metafactory`, có trường hợp dùng `altMetafactory`) qua thuộc tính `BootstrapMethods` của class file.
4. Với lambda có thân biểu thức/câu lệnh, `javac` thường sinh một method implementation dạng `lambda$...` trong class chứa biểu thức. Với method reference, bootstrap có thể trỏ thẳng tới method/constructor được tham chiếu, nên không nhất thiết có một `lambda$...` method.
5. Lúc chạy, JVM liên kết `invokedynamic` với factory/implementation phù hợp. Cách hiện thực object của lambda là chi tiết runtime, có thể thay đổi giữa các bản JDK.

**Hai thời điểm phải tách biệt:** biểu thức lambda/method reference được đánh giá để tạo **functional object**; lời gọi `apply`, `get`, `run` hoặc SAM tương ứng trên object ấy mới thực thi hành vi. Lệnh `invokedynamic` tạo lambda không đồng nghĩa tự chạy thân lambda.

Đích học tập là đọc được cấu trúc **source → class file → bootstrap linkage → gọi SAM**, thay vì ghi nhớ những chỉ số trong constant pool vốn có thể thay đổi.

## 2. Functional interface và target typing

Lambda/method reference cần một **target functional interface** để compiler biết kiểu của tham số, kiểu trả về và hành vi mong đợi. Chúng thường xuất hiện ở phép gán, đối số method, return expression hoặc cast có target type phù hợp.

~~~java
// Các ví dụ minh họa độc lập ở mức biểu thức, không phải file chạy.
java.util.function.IntUnaryOperator f = x -> x + 1;
java.util.function.Function<String, String> trim = String::trim;
java.util.function.Supplier<StringBuilder> make = StringBuilder::new;
~~~

Ở đây:

- `IntUnaryOperator` có SAM `int applyAsInt(int operand)`. Lambda `x -> x + 1` nhận `int`, trả `int`, tránh boxing.
- `Function<String,String>` có SAM `R apply(T t)`. Với `String::trim`, đối số `String` trở thành *receiver* của instance method `trim()`.
- `Supplier<StringBuilder>` có SAM `StringBuilder get()`. Constructor reference `StringBuilder::new` tạo object khi `get()` được gọi, không phải tại thời điểm gán reference.

Ví dụ `x -> x + 1` không phải một method Java khai báo độc lập với một “kiểu lambda” cố định; kiểu của biểu thức được xác định dựa vào ngữ cảnh. Cùng hình thức lambda có thể tương thích nhiều functional interfaces khác nhau. Method reference cũng cần kiểm tra chữ ký phù hợp, overload resolution và access control trước khi có thể biên dịch.

Một functional interface có thể có nhiều default/static methods, nhưng có đúng một abstract method liên quan theo quy tắc SAM. Các public methods từ `Object` không tự khiến interface mất tính functional.

## 3. Chương trình Java 17+ đầy đủ để thực hành

Tạo file `src/lesson/LambdaBytecodeDemo.java` với nội dung sau:

~~~java
package lesson;

import java.util.Locale;
import java.util.function.Function;
import java.util.function.IntUnaryOperator;
import java.util.function.Supplier;

public final class LambdaBytecodeDemo {
    private final String prefix;

    public LambdaBytecodeDemo(String prefix) {
        this.prefix = prefix;
    }

    private String decorate(String text) {
        return prefix + text;
    }

    public static String upper(String text) {
        return text.toUpperCase(Locale.ROOT);
    }

    public static void main(String[] args) {
        int offset = 3;

        IntUnaryOperator capturedLambda = x -> x + offset;
        Function<String, String> staticReference = LambdaBytecodeDemo::upper;
        Function<String, String> unboundReference = String::trim;

        LambdaBytecodeDemo demo = new LambdaBytecodeDemo(">");
        Function<String, String> boundReference = demo::decorate;
        Supplier<StringBuilder> constructorReference = StringBuilder::new;

        System.out.println(capturedLambda.applyAsInt(7));
        System.out.println(staticReference.apply("java"));
        System.out.println("[" + unboundReference.apply("  hi  ") + "]");
        System.out.println(boundReference.apply("ok"));
        System.out.println(constructorReference.get().length());
    }
}
~~~

Các biểu thức được chọn để so sánh **năm trường hợp**:

| Biểu thức | Loại | SAM | Dữ liệu được liên kết khi tạo object |
| --- | --- | --- | --- |
| `x -> x + offset` | Lambda bắt local variable | `IntUnaryOperator.applyAsInt(int)` | Giá trị của `offset` |
| `LambdaBytecodeDemo::upper` | Static method reference | `Function.apply(Object)` sau type erasure | Không có receiver |
| `String::trim` | Unbound instance method reference | `Function.apply(Object)` | Receiver là tham số SAM khi gọi |
| `demo::decorate` | Bound instance method reference | `Function.apply(Object)` | Object `demo` được đánh giá và giữ làm receiver |
| `StringBuilder::new` | Constructor reference | `Supplier.get()` | Không tạo `StringBuilder` trước khi gọi `get()` |

Biên dịch và chạy từ thư mục có `src/` bằng JDK 17 trở lên:

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 -g -d out src/lesson/LambdaBytecodeDemo.java
java -cp out lesson.LambdaBytecodeDemo
~~~

Stdout đầy đủ:

~~~text
10
JAVA
[hi]
>ok
0
~~~

`--release 17` buộc compiler tuân theo Java 17 về ngôn ngữ, class file target và Java SE API có sẵn. Nó không có nghĩa mọi build của mọi phiên bản `javac` sẽ có cùng số thứ tự constant pool, offset bytecode hoặc cùng bytecode implementation. `-g` thêm debug information giúp đọc thông tin dòng/biến khi công cụ hỗ trợ, nhưng không quyết định cơ chế lambda.

Trên Windows PowerShell, nếu không có Bash, tạo output folder bằng `New-Item -ItemType Directory -Force out`; hai lệnh `javac` và `java` còn lại giữ nguyên vì classpath chỉ có một thư mục.

## 4. Đọc bytecode với javap

Sau khi compile:

~~~bash
javap -classpath out -c -p lesson.LambdaBytecodeDemo
javap -classpath out -c -p -v lesson.LambdaBytecodeDemo
~~~

Vai trò của các tùy chọn:

- `-classpath out`: tìm class đã biên dịch, không phải source file.
- `-c`: hiển thị instructions và bytecode của các method.
- `-p`: hiển thị cả private methods. Cần thiết vì compiler có thể sinh `private static synthetic lambda$main$0(...)`.
- `-v`: hiển thị thông tin class file chi tiết, trong đó có constant pool, attributes, `BootstrapMethods`, `InnerClasses`, cùng MethodHandle/MethodType khi có.

Nên đọc đầu tiên ở method `main`, sau đó tìm từ khóa:

~~~text
invokedynamic
BootstrapMethods
LambdaMetafactory
lambda$main$
MethodHandle
MethodType
~~~

Các từ khóa trên là **dấu hiệu tìm kiếm**, không phải một bản dump hoàn chỉnh. Một class có thể chứa `invokedynamic` từ tính năng Java khác. Trong chính ví dụ này, phép ghép chuỗi `"[" + ... + "]"` hoặc `prefix + text` cũng có thể được biên dịch bằng bootstrap `StringConcatFactory.makeConcatWithConstants`. Vì vậy **không đếm tất cả `invokedynamic` rồi kết luận số lambda**; phải kiểm tra bootstrap của từng call site.

### 4.1. Cách diễn giải một đoạn main bytecode

Một đoạn **minh họa lược bỏ số constant-pool index, offset và mã phụ** có hình thức:

~~~text
iload ...                             // Đưa offset đã capture lên stack
invokedynamic ... applyAsInt:(I)Ljava/util/function/IntUnaryOperator;
astore ...                            // Lưu functional object

...                                   // Các biểu thức reference khác
invokedynamic ... apply:()Ljava/util/function/Function;
invokedynamic ... apply:()Ljava/util/function/Function;

aload ...                             // Đưa receiver demo lên stack
invokedynamic ... apply:(Llesson/LambdaBytecodeDemo;)Ljava/util/function/Function;

invokedynamic ... get:()Ljava/util/function/Supplier;
~~~

Đây là **sơ đồ chữ ký**, không phải output literal của `javap`. Compiler có thể thêm instructions cho null check của bound receiver, cast, local variables, tạo object và xử lý ghép chuỗi. Thứ tự/chỉ số constant pool tùy JDK.

Ý nghĩa quan trọng:

- Phần trong ngoặc của descriptor `(I)Ljava/util/function/IntUnaryOperator;` là **tham số được capture khi tạo functional object**: một `int` (offset). Đó **không phải** danh sách tham số đầy đủ của SAM.
- Descriptor `()Ljava/util/function/Function;` không có captured argument trong hai method references static và unbound ở ví dụ.
- Descriptor `(Llesson/LambdaBytecodeDemo;)Ljava/util/function/Function;` thể hiện bound receiver được truyền vào factory tạo functional object.
- Các lệnh `invokeinterface Function.apply`, `invokeinterface IntUnaryOperator.applyAsInt`, `invokeinterface Supplier.get` xuất hiện tại **điểm thực sự gọi** hành vi qua SAM.

Cần phân biệt `invokedynamic` ở lúc tạo object của functional interface với `invokeinterface` khi mã chương trình gọi SAM. Implementation được JVM liên kết cho call site quyết định lời gọi cuối cùng diễn ra thế nào; không suy từ tên `apply` rằng Java đang gọi trực tiếp method `upper` ngay trong lệnh `invokedynamic`.

## 5. BootstrapMethods và LambdaMetafactory

Ở class file có `invokedynamic`, constant pool chứa các entries như `CONSTANT_InvokeDynamic`, `CONSTANT_MethodHandle` và `CONSTANT_MethodType`; attribute `BootstrapMethods` lưu bootstrap method và static arguments. Mỗi instruction `invokedynamic` có thể tham chiếu một entry bootstrap cùng tên hoặc khác tên.

Đối với lambda/method reference thông thường, bootstrap thường là:

~~~text
java/lang/invoke/LambdaMetafactory.metafactory
~~~

Ở mức khái niệm, bootstrap thường kết hợp ba thông tin nền tảng:

1. **SAM method type**: kiểu erased của method functional interface mà object sẽ thực hiện, ví dụ `(Ljava/lang/Object;)Ljava/lang/Object;` cho `Function.apply`.
2. **Implementation method handle**: method thực sự sẽ chạy, ví dụ helper compiler sinh hoặc `LambdaBytecodeDemo.upper`, `String.trim`, `LambdaBytecodeDemo.decorate`, constructor `StringBuilder.<init>`.
3. **Instantiated method type**: chữ ký mục tiêu sau khi suy luận/áp kiểu cụ thể, ví dụ `(Ljava/lang/String;)Ljava/lang/String;` cho `Function<String,String>`.

Bootstrap có thể thêm bridge methods/flags hoặc xử lý trường hợp serializable/marker interfaces qua `altMetafactory`. Không nên khẳng định mọi lambda trên mọi compiler đều dùng đúng một dạng `metafactory` hay có cùng danh sách static arguments.

**Ba tầng kiểu dễ bị nhầm:**

~~~text
invokedynamic factory descriptor    : tham số capture → functional-interface instance
SAM signature (erased)               : Object → Object, ví dụ Function.apply
Instantiated SAM signature           : String → String, sau type inference
Implementation method                : static/instance/constructor/helper được liên kết
~~~

Ví dụ `Function<String,String> f = String::trim` có SAM erased `Object apply(Object)`, nhưng implementation handle là `String.trim():String`. Runtime có thể cần casts/adapters để phù hợp hai chữ ký. Không nhất thiết có một method Java bridge nhìn thấy trong source.

### 5.1. Vì sao helper thường tên lambda$...?

Với lambda `x -> x + offset`, compiler cần biểu diễn phần thân phép cộng dưới dạng executable method. Thông thường `javap -p -c` có thể hiển thị một method **private static synthetic** với tên dạng `lambda$main$0` và logic tương đương:

~~~text
iload_0           // int offset đã capture
iload_1           // int x từ SAM
iadd              // offset + x
ireturn
~~~

Đoạn này **chỉ là minh họa logic**, không bảo đảm đúng opcode offsets, local slot layout hoặc tên method của mọi phiên bản `javac`. Compiler có thể sắp tham số theo thiết kế riêng và code được tối ưu khác. Điểm cần đọc là một handle trong bootstrap trỏ tới implementation logic của lambda.

**Không gọi trực tiếp `lambda$main$0` từ mã Java.** Đó là implementation detail, tên có thể thay đổi; khả năng truy cập ở bytecode có thể được JVM xử lý qua lookup do bootstrap cung cấp.

Method reference `LambdaBytecodeDemo::upper` thường có thể liên kết tới method `upper` trực tiếp (static), `String::trim` tới instance method, `StringBuilder::new` tới constructor. **Đừng ép phải tìm đúng một helper `lambda$...` cho mỗi reference.** Compiler vẫn có thể sinh adapter trong một số trường hợp (chuyển đổi chữ ký, varargs, access hoặc corner cases), nên kết luận phải dựa trên dump thực tế.

## 6. Cùng là instance method reference, bound và unbound khác nhau

Hai biểu thức:

~~~java
Function<String, String> unbound = String::trim;
Function<String, String> bound = demo::decorate;
~~~

đều cung cấp một instance method nhưng có cách xác định receiver rất khác.

**Unbound `String::trim`:** chưa có object `String` cụ thể lúc tạo functional object. Khi chạy `unbound.apply(" hi ")`, chính tham số `" hi "` là receiver, tương đương với `" hi ".trim()`.

**Bound `demo::decorate`:** biểu thức `demo` được đánh giá **một lần ở thời điểm tạo method reference**. Reference giữ receiver ấy; khi chạy `bound.apply("ok")`, nó dùng receiver đã liên kết, tương đương `demo.decorate("ok")`. Nếu receiver null, bound instance method reference có thể ném `NullPointerException` **khi tạo method reference**, trước lần gọi `apply`.

Điều này giải thích tại sao descriptor factory của bound reference có một tham số receiver được capture, còn unbound reference ở ví dụ thường không cần captured receiver. `Object::toString` gắn receiver từ tham số SAM của nó là một ví dụ unbound tương tự khi target type phù hợp.

### 6.1. Captured local variable và effectively final

Trong ví dụ, `offset` có giá trị `3` và không bị gán lại; nó là *effectively final*. Java yêu cầu local variables được lambda (hoặc anonymous/local inner class theo quy tắc liên quan) capture phải final hoặc effectively final.

Đoạn sau cố ý sai:

~~~java
// Không phải chương trình độc lập; nếu nằm cùng method:
int offset = 3;
IntUnaryOperator add = x -> x + offset;
offset = 4;  // Compile error: offset không còn effectively final.
~~~

Nếu muốn trạng thái thay đổi theo thời gian, thiết kế một object state có chủ đích hoặc quản lý state bên ngoài phù hợp. Đừng dùng mảng một phần tử hoặc biến static tùy tiện chỉ để né compile error mà che giấu vấn đề đồng thời.

**Capture giá trị local không có nghĩa “giữ một local variable sống trên stack” sau khi method kết thúc.** Với primitive như `int offset`, giá trị tại thời điểm tạo lambda có thể được truyền như captured argument. Với object reference được capture, giá trị reference được giữ; trạng thái bên trong object vẫn có thể thay đổi nếu object mutable. Tương tự, bound method reference giữ receiver object được đánh giá tại lúc tạo reference.

## 7. Static reference, constructor reference và lambda viết lại tương đương

So sánh những dạng dưới đây về mặt hành vi trong ngữ cảnh phù hợp:

| Dạng | Viết bằng lambda tương ứng | Nét bytecode cần tìm |
| --- | --- | --- |
| `LambdaBytecodeDemo::upper` | `s -> LambdaBytecodeDemo.upper(s)` | Implementation method handle thường trỏ thẳng static method |
| `String::trim` | `s -> s.trim()` | Handle tới instance method; receiver đến từ tham số SAM |
| `demo::decorate` | `s -> demo.decorate(s)` | Receiver `demo` được capture |
| `StringBuilder::new` | `() -> new StringBuilder()` | Handle tới constructor |
| `x -> x + offset` | Giữ nguyên lambda body | Có logic compiler sinh để cộng hai giá trị |

Đây là các ví dụ **tương đương về kết quả trong ngữ cảnh ví dụ**, không phải cam kết về bytecode hoặc thời điểm đánh giá hoàn toàn đồng nhất trong mọi biểu thức. Đặc biệt, bound method reference đánh giá receiver ngay khi tạo; một lambda `s -> demo.decorate(s)` có thể chỉ dereference receiver khi lambda được gọi. Khi receiver null hoặc expression tạo receiver có side effect, hai hình thức có thể khác thời điểm gây lỗi/tác dụng phụ.

Constructor reference `StringBuilder::new` không phải phép khởi tạo object ở dòng gán `Supplier`. Nó cung cấp logic khởi tạo, được kích hoạt khi gọi `get()`. Trong class file, implementation handle cho constructor có thể thuộc dạng method handle `REF_newInvokeSpecial`, thay vì một `invokestatic` như static method reference.

## 8. Tại sao không thấy file .class mới cho mỗi lambda?

Trước Java 8, anonymous inner class thường dẫn đến class file riêng như `Outer$1.class`. Để đối chiếu, tạo file **độc lập** `src/lesson/AnonymousContrast.java`:

~~~java
package lesson;

public final class AnonymousContrast {
    public static void main(String[] args) {
        Runnable anonymous = new Runnable() {
            @Override
            public void run() {
                System.out.println("anonymous");
            }
        };

        Runnable lambda = () -> System.out.println("lambda");

        anonymous.run();
        lambda.run();
    }
}
~~~

Biên dịch:

~~~bash
javac --release 17 -encoding UTF-8 -d out src/lesson/AnonymousContrast.java
java -cp out lesson.AnonymousContrast
~~~

Stdout:

~~~text
anonymous
lambda
~~~

Với `javac` thông thường, anonymous class được biểu diễn bằng một class file riêng (ví dụ `AnonymousContrast$1.class`). Lambda dùng `invokedynamic` và bootstrap linkage; lúc compile không nhất thiết có class file trên đĩa tương ứng tên lambda. Nếu quan sát runtime, JVM có thể tạo implementation class động. Trên HotSpot từ những bản Java hiện đại, lambda implementation có thể sử dụng **hidden classes**; đó là chi tiết runtime, không nên suy rằng `javac` luôn sinh một class file public hoặc stable cho mỗi lambda.

Đừng phụ thuộc vào kết quả `lambda.getClass().getName()`, tên object class, số lượng generated classes, cách cache singleton cho non-capturing lambda hay identity của các lambda objects để đưa ra giả định ngôn ngữ. Quy tắc đáng tin cậy nằm ở **functional interface**, capture, cách đánh giá biểu thức và hành vi SAM. Runtime có quyền thay đổi chiến lược hiện thực.

### 8.1. Khác biệt của this và shadowing

Trong lambda, `this` và `super` giữ nghĩa theo **ngữ cảnh bao quanh**; lambda không đưa ra một lexical `this` mới giống như anonymous inner class. Trong anonymous class, `this` trỏ tới object anonymous class. Điều này giải thích một số khác biệt khi chuyển từ anonymous class sang lambda dù cùng triển khai `Runnable`.

Cơ chế lambda cũng có thể hạn chế biến local shadowing so với phạm vi class khác; code phải tuân theo quy tắc scope của Java. Đừng chuyển tự động anonymous class thành lambda chỉ dựa vào cùng chữ ký SAM nếu implementation phụ thuộc identity của `this` hoặc khả năng truy cập members.

## 9. invokedynamic trong Java không chỉ dành cho lambda

Từ Java 9, `javac` thường dùng `invokedynamic` cho **string concatenation**, ví dụ `"[" + s + "]"`, với bootstrap `java.lang.invoke.StringConcatFactory.makeConcatWithConstants`. Java còn có những tính năng dùng bootstrap khác (ví dụ dynamic constants qua `ConstantDynamic`, tùy ngữ cảnh).

Vì thế, khi đọc output `javap -v`:

1. Tìm `invokedynamic` trong method đang phân tích.
2. Tìm entry `BootstrapMethods` tương ứng qua bootstrap index (đừng dùng “số dòng trông gần nhất”).
3. Xác định bootstrap `LambdaMetafactory` hay `StringConcatFactory`.
4. Đọc descriptor của factory call site và method handle arguments.
5. Đối chiếu với `invokeinterface` nơi SAM được gọi và với những method `lambda$...` được compiler sinh.

Có thể dùng lệnh lọc trong shell tùy môi trường, nhưng **đừng chỉ grep `invokedynamic` rồi bỏ mất `BootstrapMethods`**. Đọc toàn bộ hai phần hoặc ghi chú index kết nối giữa chúng; tên constant pool tự động đánh số có thể khác giữa các bản JDK.

## 10. Erasure, adapters và bridge methods trong bytecode

`Function<String,String>` là generic tại source level, nhưng class file invocation của `Function.apply` về cơ bản dùng descriptor erased:

~~~text
(Ljava/lang/Object;)Ljava/lang/Object;
~~~

Vì thế, code gọi `Function.apply` có thể có `checkcast java/lang/String` sau đó. Bootstrap của lambda có thể chỉ định instantiated signature `(Ljava/lang/String;)Ljava/lang/String;`, còn implementation method handle có chữ ký cụ thể `String -> String`.

Dấu hiệu cần nhận diện:

- **Erased SAM signature** thuộc JVM-level method descriptor của interface.
- **Instantiated method type** mô tả cách target functional interface được chuyên biệt trong phép chuyển đổi hiện tại.
- **Bridge/adaptation** giúp các chữ ký khớp nhau theo quy tắc linkage; không mặc định rằng mọi lời gọi phải có một adapter method `lambda$...` hiển thị riêng.
- Với functional interface primitive-specialized như `IntUnaryOperator`, SAM `applyAsInt(int)` dùng descriptor primitive `(I)I`, tránh phần boxing/unboxing do `Function<Integer,Integer>` có thể phát sinh.
- Overload resolution và generic type inference là công việc compile-time; JVM không giữ đầy đủ type arguments generic dưới dạng những kiểu runtime mới cho mỗi instantiation.

Tính đúng đắn của method reference còn phụ thuộc accessibility và type compatibility: chẳng hạn method private chỉ có thể được tham chiếu từ code có quyền truy cập phù hợp; target SAM với số lượng/kiểu tham số sai sẽ bị `javac` từ chối trước khi JVM chạy `invokedynamic`.

## 11. Khác biệt giữa capture và lời gọi SAM về hiệu năng

Khi quan sát bytecode, không nên rút ra kết luận cứng như “mỗi lần lặp tạo đúng một object”, “method reference nhanh hơn lambda” hay “invokedynamic chậm hơn lời gọi thường”.

- Một **non-capturing** lambda hoặc method reference có thể được runtime tái sử dụng instance, nhưng chương trình không được dựa vào object identity hay cơ chế cache cụ thể.
- Một **capturing** lambda cần mang theo dữ liệu capture theo ngữ nghĩa; số lượng object được cấp phát thực tế còn phụ thuộc runtime, JIT escape analysis và các tối ưu khác.
- `invokedynamic` ban đầu có hoạt động linkage; sau đó call site có thể được JIT tối ưu/inlining. Không thể suy chi phí thực thi chỉ từ sự có mặt của instruction.
- Phép nối chuỗi, boxing, allocation trong thân lambda hoặc thao tác I/O có thể chi phối runtime cost nhiều hơn sự khác nhau giữa hai cú pháp.
- Benchmark muốn so sánh phải dùng công cụ phù hợp như JMH, có warm-up, tránh dead-code elimination và ghi rõ JDK/VM/flags. Một vài lần `System.nanoTime` không đủ để kết luận.

Hãy dùng `javap` để **giải thích cơ chế**, profiler hoặc microbenchmark chuẩn để **đo hiệu năng**. Hai hoạt động trả lời hai câu hỏi khác nhau.

## 12. Các lỗi phổ biến khi phân tích bytecode lambda

| Nhận định/triệu chứng | Vì sao sai hoặc chưa đủ | Cách kiểm tra đúng |
| --- | --- | --- |
| “Một lambda luôn là một class file `$1.class`.” | Lẫn lambda với anonymous class; lambda thường liên kết qua `invokedynamic` | So sánh `javap -c -p -v` và danh sách class files |
| “Mọi `invokedynamic` là lambda.” | String concatenation cũng có thể dùng `invokedynamic` | Tra cứu entry `BootstrapMethods` cho call site |
| “Thấy `invokedynamic` nghĩa là lambda body chạy ngay.” | Factory tạo object; hành vi chạy khi gọi SAM | Tìm `invokeinterface apply/get/run` |
| “Mỗi method reference sinh một `lambda$...` method.” | Có thể dùng direct method handle; adapter chỉ khi cần | Đọc implementation handle trong bootstrap |
| “String::trim và demo::decorate capture như nhau.” | Unbound lấy receiver từ SAM argument; bound giữ receiver ngay lúc tạo | So descriptor factory có/không có receiver |
| “Lambda capture local variable có thể bị thay đổi tùy ý.” | Local variable phải final/effectively final | Kiểm tra assignment sau thời điểm capture |
| “Tên/địa chỉ class lambda ở runtime là API ổn định.” | Runtime có thể dùng hidden class, cache, đổi implementation | Dựa vào SAM và Java semantics |
| “Có `--release 17` thì `javap` ở mọi JDK giống hệt.” | Toolchain/version có thể đổi constant pool numbering/implementation details | So sánh ý nghĩa bootstrap, descriptor, capture |
| “Method reference luôn tránh allocation.” | Object/capture vẫn có thể xuất hiện; JVM tối ưu tùy tình huống | Đo bằng benchmark/profiler |
| “Function<String,String> có descriptor SAM trực tiếp String → String.” | Erasure đưa `apply(Object)` ở JVM-level | Đọc cả erased và instantiated method types |

## 13. Quy trình tự phân tích một lambda mới

Với một biểu thức `target = expression`, thực hiện theo thứ tự:

1. **Xác định target functional interface** và chữ ký SAM ở source level, ví dụ `Function<String,String>`.
2. **Phân loại biểu thức**: lambda có body hay method reference; nếu reference, đó là static, bound instance, unbound instance, array constructor hay class constructor?
3. **Liệt kê captured variables/receiver** tại thời điểm tạo biểu thức. Local capture phải effectively final; bound receiver được đánh giá ngay.
4. **Biên dịch chương trình nhỏ độc lập**, dùng `javac --release 17 -g -d out ...`, rồi kiểm tra stdout để xác nhận ngữ nghĩa.
5. **Đọc bytecode** bằng `javap -classpath out -c -p -v ...`. Tìm entry `invokedynamic` tạo functional interface và `invokeinterface` lúc gọi SAM.
6. **Đọc BootstrapMethods**, tìm `LambdaMetafactory`, SAM type, implementation handle, instantiated method type; giải thích captured arguments qua descriptor factory.
7. **Xem helper methods** `lambda$...` nếu có, đối chiếu logic với source. Nếu không có, kiểm tra handle trỏ trực tiếp tới method/constructor nào.
8. **Phân biệt đặc thù JDK/VM** (constant pool index, tên helper, runtime hidden class, tối ưu) khỏi hợp đồng ngôn ngữ (target typing, capture, hành vi).

### Bài thực hành mở rộng

Bắt đầu từ `LambdaBytecodeDemo`. Lần lượt đổi chỉ **một** biểu thức rồi compile và đọc lại:

- Đổi `x -> x + offset` thành `x -> x * 2`. So descriptor factory khi lambda không capture; dự đoán stdout của `applyAsInt(7)` là `14`.
- Đổi static method reference thành lambda `s -> LambdaBytecodeDemo.upper(s)`. Quan sát implementation handle có thể từ direct static method chuyển sang helper `lambda$...` trong dump cụ thể.
- Giữ `demo::decorate` và thử `Function<String,String> f = ((LambdaBytecodeDemo) null)::decorate;` trong file thử riêng: nhận diện thời điểm `NullPointerException` khi đánh giá bound receiver.
- Đổi `String::trim` thành `String::strip` với JDK 17+; giải thích khác biệt về xử lý khoảng trắng Unicode và nhận diện `REF_invokeVirtual` hoặc dạng tương đương trong bootstrap.
- Chạy lại trên một bản JDK khác nếu có. So sánh **bootstrap name, method types và hành vi**; đừng kỳ vọng số constant pool indexes hoặc class implementation giống hệt.

Kiến thức quan trọng nhất là liên kết được bốn tầng: **biểu thức Java có target type → factory `invokedynamic` trong bytecode → `LambdaMetafactory` cùng method handle implementation → thực thi qua SAM khi chạy**. Hiểu bốn tầng này giúp đọc đúng lambda, method reference và sự khác nhau giữa mã nguồn ngắn gọn với code JVM thật sự thực thi.
