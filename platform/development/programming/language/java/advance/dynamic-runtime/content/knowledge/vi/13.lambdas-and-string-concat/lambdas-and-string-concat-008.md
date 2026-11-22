# 13.8. Quan sát javap và tách hợp đồng ngôn ngữ khỏi chi tiết do javac sinh ra

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Dùng `javac` và `javap` để quan sát bytecode, constant pool, các method được compiler sinh thêm và bảng `BootstrapMethods` của một class chứa **lambda**, **method reference** và **nối chuỗi bằng toán tử +**.
- Giải thích tại sao bản biên dịch thử nghiệm có thể chứa `invokedynamic`, `LambdaMetafactory`, `StringConcatFactory`, các method tên `lambda$...` hoặc `StringBuilder`, nhưng **tên và hình dạng bytecode cụ thể không phải hợp đồng Java source**.
- Đọc descriptor của một `invokedynamic` để phân biệt **captured variables** tại thời điểm tạo lambda với **tham số SAM** khi gọi lambda.
- Phân biệt các điều được Java Language Specification (JLS) bảo đảm (kiểu đích functional interface, quy tắc capture, thứ tự đánh giá biểu thức, kết quả nối chuỗi) với lựa chọn của compiler/JDK/JVM.
- Thực hiện kiểm tra có thể lặp lại, so sánh `--release 8` và `--release 17` một cách công bằng, và không rút kết luận về hiệu năng hoặc object identity chỉ từ `javap`.

**Ngữ cảnh:** Java Advance – dynamic-runtime; chủ đề cha là **Lambda và nối chuỗi**. Ví dụ sử dụng Java 17+ và chỉ đọc class file do chính ví dụ tạo ra. Khi làm việc với Java phiên bản khác, một số chi tiết bytecode có thể thay đổi.

## 1. Ba tầng cần tách bạch

Lý do cần học `javap` là để thấy **compiler đã thực hiện một lựa chọn cụ thể**, chứ không phải để biến lựa chọn đó thành định nghĩa của ngôn ngữ Java.

~~~text
Java source:     () -> expr, Type::method, "x=" + value
      |
      | javac --release <version>
      v
Class file:      constant pool, Code, BootstrapMethods, invokedynamic...
      |
      | JVM verifier, linkage, runtime optimization / JIT
      v
Hành vi chạy:    gọi lambda, tạo String, tối ưu, thu gom rác...
~~~

| Tầng | Câu hỏi đúng | Loại bằng chứng |
| --- | --- | --- |
| **Ngôn ngữ Java (JLS)** | Lambda có target type gì? Capture local như thế nào? `+` với String tạo giá trị nào? Thứ tự đánh giá operand thế nào? | Quy tắc JLS, kiểm thử hành vi |
| **Class file (JVMS + đầu ra javac)** | Compiler này sinh bytecode nào? Có `invokedynamic` không? `BootstrapMethods` tham chiếu tới đâu? | `javap -c -p -v`, `javap -s`, class file |
| **Runtime và JIT** | Lambda được hiện thực bằng object/runtime class nào? Có allocation, inline hoặc constant folding lúc chạy không? | Công cụ profiling/JFR/JMH, đặc tả JVM liên quan |

**Không đánh đồng:** `javap` là trình tháo dịch **class file**, không phải công cụ hiển thị máy mã JIT thực tế. Một dòng `invokedynamic` trong class file không chứng minh JVM thực thi một bootstrap method ở mỗi lần gọi. Một dòng `new StringBuilder` không chứng minh runtime nhất định phải cấp phát một object `StringBuilder` vật lý tại mỗi lần chạy.

### 1.1. “Hợp đồng ngôn ngữ” nghĩa là gì?

Đó là hành vi mà chương trình Java đúng phải quan sát được theo đặc tả, bất kể compiler chọn cách hạ source xuống bytecode như thế nào. Ví dụ:

- Lambda được **định kiểu theo functional interface** ở ngữ cảnh phù hợp.
- Local variable từ enclosing scope mà lambda sử dụng phải `final` hoặc **effectively final** (đối với local/parameter cần capture).
- Nối chuỗi String bằng `+` phải cho **giá trị String tương ứng với string conversion** của các operand và giữ quy tắc đánh giá của Java.
- Biểu thức String là **compile-time constant expression** khi thỏa điều kiện JLS thì có hành vi hằng biên dịch tương ứng.

Ngược lại, tên private helper `lambda$makeAdder$0`, số thứ tự `#19` trong constant pool, recipe ký tự cho `StringConcatFactory`, hay việc runtime dùng hidden class đều **không phải API source** để ứng dụng dựa vào.

### 1.2. “Chi tiết javac sinh ra” nghĩa là gì?

Với một bản `javac` nhất định, target version nhất định và một đoạn source nhất định, compiler phát hành một class file cụ thể. Các chi tiết có thể bao gồm:

- Một hay nhiều instruction `invokedynamic` và các entry `CONSTANT_InvokeDynamic`.
- Bootstrap method handle tới `java/lang/invoke/LambdaMetafactory.metafactory`, `altMetafactory`, hoặc `StringConcatFactory.makeConcatWithConstants`.
- Private method phụ trợ để chứa body lambda.
- Cách chia/gộp một chuỗi nối `+` thành các call site.
- Cách chọn bytecode như `ldc`, `invokevirtual`, `invokestatic`, `StringBuilder.append`.
- Constant-pool index, tên method tổng hợp, thứ tự bootstrap entry, flag synthetic và số offset bytecode.

Quan sát chúng có ích khi debug, audit bytecode, học cơ chế JVM và nghiên cứu hiệu năng. Nhưng API ứng dụng không nên buộc kết quả của `javap` phải giữ nguyên từng dòng giữa các bản JDK.

## 2. Bộ công cụ javac / javap tối thiểu

`javac` biên dịch source thành `.class`; `javap` đọc class file đó. Có thể kiểm tra phiên bản:

~~~bash
java -version
javac -version
javap -version
~~~

Lệnh dưới đây giả sử đang dùng **JDK 17 trở lên**, và ta chủ động chọn Java 17 cho bản thử nghiệm:

~~~bash
javac --release 17 -encoding UTF-8 LambdaConcatObservation.java EvaluationOrderDemo.java
java LambdaConcatObservation
java EvaluationOrderDemo
javap -c -p LambdaConcatObservation
javap -v -p LambdaConcatObservation
javap -c -p EvaluationOrderDemo
~~~

Ý nghĩa các option:

| Option | Tác dụng | Lưu ý |
| --- | --- | --- |
| `javac --release 17` | Chọn ngữ nghĩa source, target classfile và public platform API tương ứng release 17 | Không có nghĩa compiler thực thi chính xác thuật toán của `javac` phiên bản 17 |
| `javac -encoding UTF-8` | Đọc source theo UTF-8 | Giữ ổn định khi có chú thích/chữ tiếng Việt |
| `javap -c` | Hiển thị mã instruction của method có Code attribute | Không tự hiện đầy đủ BootstrapMethods |
| `javap -p` | Hiển thị cả member private | Hữu ích để thấy helper `lambda$...` |
| `javap -v` | Hiển thị thông tin chi tiết: constant pool, flags, BootstrapMethods... | Output dài; số thứ tự có thể thay đổi |
| `javap -s` | In JVM descriptors | Dùng khi khó phân biệt kiểu source và descriptor |
| `javac -g` và `javap -l` | Thêm/xem thông tin line và local-variable debug | Metadata debug không định nghĩa semantics |

Nếu class nằm trong thư mục output riêng:

~~~bash
# Fragment lệnh shell: class đã biên dịch vào out17.
javap -c -p -classpath out17 LambdaConcatObservation
~~~

Tránh tháo dịch nhầm một class cùng tên nằm nơi khác trong classpath. Với dự án có nhiều module, jar hoặc classloader, xác nhận class file nào được đọc trước khi kết luận.

### 2.1. Vì sao cần cố định release và ghi lại JDK thực tế?

Hai biến ảnh hưởng tới so sánh:

1. **Target release**: ví dụ `--release 8` so với `--release 17`. Nó ảnh hưởng classfile target và có thể ảnh hưởng chiến lược emit bytecode.
2. **Phiên bản compiler đang chạy**: `javac 17`, `javac 21`, `javac 24`... Có thể chọn cùng target 17 nhưng vẫn được phép thay cách emit chi tiết trong giới hạn đặc tả.

Báo cáo quan sát có trách nhiệm nên ghi: **compiler version, `--release`, source, lệnh javap và đoạn classfile đã xem**. Không ghi “Java 17 bắt buộc tạo đúng method `lambda$...`” chỉ vì mình thấy nó trong một lần thử.

## 3. Ví dụ chạy được 1: lambda, method reference và string concat

Lưu nguyên văn nội dung sau thành **LambdaConcatObservation.java**.

~~~java
import java.util.Locale;
import java.util.function.Function;
import java.util.function.IntUnaryOperator;
import java.util.function.Supplier;

public class LambdaConcatObservation {
    private static String shout(String text) {
        return text.toUpperCase(Locale.ROOT);
    }

    static IntUnaryOperator makeAdder(int step) {
        return input -> input + step;
    }

    static IntUnaryOperator makeDoubler() {
        return input -> input * 2;
    }

    static String format(String name, int count) {
        return "item=" + name + ", count=" + count;
    }

    public static void main(String[] args) {
        IntUnaryOperator doubleIt = makeDoubler();
        IntUnaryOperator addFive = makeAdder(5);
        Function<String, String> ref = LambdaConcatObservation::shout;
        Supplier<String> greeting = () -> "hello";
        String constant = "ab" + "cd";
        String missing = null;

        System.out.println("double=" + doubleIt.applyAsInt(7));
        System.out.println("addFive=" + addFive.applyAsInt(7));
        System.out.println("ref=" + ref.apply("java"));
        System.out.println("supplier=" + greeting.get());
        System.out.println("concat=" + format("A", 3));
        System.out.println("constant=" + constant);
        System.out.println("missing=" + ("value=" + missing));
    }
}
~~~

Biên dịch và thực thi:

~~~bash
javac --release 17 -encoding UTF-8 LambdaConcatObservation.java
java LambdaConcatObservation
~~~

**Stdout chính xác**:

~~~text
double=14
addFive=12
ref=JAVA
supplier=hello
concat=item=A, count=3
constant=abcd
missing=value=null
~~~

Những điều đầu tiên cần kiểm tra **không cần xem bytecode**:

- `makeDoubler` trả một `IntUnaryOperator` áp dụng phép nhân hai.
- `makeAdder(5)` trả một `IntUnaryOperator` có body dùng giá trị `step=5` được capture.
- `LambdaConcatObservation::shout` là method reference khớp với functional type `Function<String,String>`.
- `"ab" + "cd"` là một constant expression; chương trình in `abcd`.
- `"value=" + missing` biến tham chiếu `null` thành phần chữ `null` theo string conversion.

**Đây là hành vi cần giữ khi đổi compiler**, ngay cả khi classfile implementation khác nhau.

## 4. Đọc javap -c: nơi có invokedynamic và nơi không cần

Chạy:

~~~bash
javap -c -p LambdaConcatObservation
~~~

Ở một bản biên dịch thử nghiệm với target release 17, phần `makeAdder` có hình thái tiêu biểu:

~~~text
static java.util.function.IntUnaryOperator makeAdder(int);
  Code:
     0: iload_0
     1: invokedynamic #19,  0  // InvokeDynamic #0:applyAsInt:(I)Ljava/util/function/IntUnaryOperator;
     6: areturn
~~~

Trong khi `makeDoubler` điển hình có:

~~~text
static java.util.function.IntUnaryOperator makeDoubler();
  Code:
     0: invokedynamic #23,  0  // InvokeDynamic #1:applyAsInt:()Ljava/util/function/IntUnaryOperator;
     5: areturn
~~~

**Các số `#19`, `#23`, `#0`, `#1`, offset `0/1/6` là minh họa từ một bản build, không phải số cố định của Java 17.** Xem tên lệnh, descriptor và bootstrap mapping mới là điều có ý nghĩa.

### 4.1. Capturing lambda: dấu hiệu trong descriptor

Với source:

~~~java
// Fragment lấy từ makeAdder(int step):
return input -> input + step;
~~~

`step` đến từ ngoài lambda body. Khi tạo lambda, compiler phải sắp xếp để **giá trị capture** đi vào implementation. Trong javap mẫu:

~~~text
invokedynamic ... applyAsInt:(I)Ljava/util/function/IntUnaryOperator;
~~~

Descriptor `(I)Ljava/util/function/IntUnaryOperator;` ở **factory site** có nghĩa:

- `(I)`: tại thời điểm tạo functional object, call site nhận **một int được capture** (`step`).
- `L...IntUnaryOperator;`: kết quả của factory site là một tham chiếu có kiểu `IntUnaryOperator`.

**Không đọc nhầm** `(I)` trong factory descriptor thành “tham số input của `applyAsInt`”. SAM `IntUnaryOperator.applyAsInt(int)` vẫn nhận một `int input` khi lambda được gọi sau đó. Hai thời điểm khác nhau:

~~~text
Tạo lambda:      makeAdder(5)   -> factory invokedynamic(step = 5)
Gọi lambda:      op.applyAsInt(7) -> body dùng input=7 và step=5
Kết quả:         12
~~~

Một bản `javac` có thể sinh private helper dạng:

~~~text
private static int lambda$makeAdder$0(int, int);
  Code:
     0: iload_1
     1: iload_0
     2: iadd
     3: ireturn
~~~

Helper nhận cả captured `step` và tham số invocation `input`. Nhưng **tên `lambda$makeAdder$0` và thứ tự helper-generated methods là chi tiết javac**, không phải thứ ứng dụng nên gọi reflection theo tên.

### 4.2. Non-capturing lambda: descriptor có thể không có capture input

`makeDoubler` có body:

~~~java
// Fragment từ chương trình:
return input -> input * 2;
~~~

Không sử dụng local variable ở enclosing method. Vì vậy bản build được quan sát có factory descriptor:

~~~text
()Ljava/util/function/IntUnaryOperator;
~~~

Không có `int step` cần truyền tới factory. Javac trong phép thử có helper:

~~~text
private static int lambda$makeDoubler$0(int);
~~~

Nhưng **đừng suy từ descriptor rỗng rằng mỗi lần gọi `makeDoubler()` buộc trả cùng object instance**. JLS cho phép implementation tái sử dụng hoặc tạo functional objects; đẳng thức tham chiếu `==` của hai lambda objects **không phải công cụ** để xác định chúng có cùng hành vi.

Nếu yêu cầu semantics là “hai phép toán giống nhau”, hãy so sánh contract nghiệp vụ chứ không dùng identity của lambda expression.

### 4.3. Method reference: thấy một cách liên kết khác

Source:

~~~java
// Fragment từ main:
Function<String, String> ref = LambdaConcatObservation::shout;
~~~

Trong một bản build, `javap` cho `main` thấy một `invokedynamic` tạo `Function`; `BootstrapMethods` có thể tham chiếu trực tiếp tới `LambdaConcatObservation.shout` qua một `MethodHandle`.

Không nhất thiết phải có method mới tên `lambda$main$...()` chỉ để chuyển tiếp lời gọi này. **Method reference vẫn chịu quy tắc target typing** của Java, nhưng compiler có thể chọn cách mã hóa implementation handle khác với lambda expression chứa body.

Điều phải học là **phương thức được chọn và hợp đồng functional interface**, không phải “method reference luôn không có helper” hoặc “luôn nhanh hơn lambda”.

### 4.4. Tại sao có lambda$main$0?

Trong ví dụ, biểu thức:

~~~java
// Fragment từ main:
Supplier<String> greeting = () -> "hello";
~~~

có body lambda. Javac thử nghiệm sinh method riêng để chứa body:

~~~text
private static java.lang.String lambda$main$0();
  Code:
     0: ldc  // String hello
     2: areturn
~~~

Tên helper ở đây **phụ thuộc compiler**, có thể thay theo sắp xếp method hoặc tối ưu. Không viết API phụ thuộc method này, không hardcode `Class.getDeclaredMethod("lambda$main$0")` và không tin rằng helper luôn có chính xác một method ứng với một lambda.

Ngoài ra, khi dùng `javap -p` thấy private helper không có nghĩa source đã trực tiếp khai báo nó. Để xác định synthetic flags, dùng `javap -v -p` và xem flag liên quan; khi xem compiled bytecode phải phân biệt source method với compiler-generated artifact.

## 5. Đọc javap -v: BootstrapMethods, constant pool và hai loại bootstrap

`javap -c` cho biết một instruction `invokedynamic` tồn tại. Để biết **liên kết đi đâu**, chạy:

~~~bash
javap -v -p LambdaConcatObservation
~~~

Tìm ba vị trí:

1. **Constant pool:** dòng `InvokeDynamic` trỏ tới một bootstrap method index và một `NameAndType`.
2. **Code của method:** instruction `invokedynamic` dùng constant-pool entry đó.
3. **BootstrapMethods:** entry chỉ ra bootstrap method handle và static bootstrap arguments, trong đó thường có implementation handle hoặc recipe của concat.

Trong output của bản thử nghiệm, phần tên bootstrap xuất hiện theo mẫu:

~~~text
BootstrapMethods:
  ... REF_invokeStatic java/lang/invoke/LambdaMetafactory.metafactory:...
  ... REF_invokeStatic java/lang/invoke/StringConcatFactory.makeConcatWithConstants:...
~~~

Các dấu `...` trong khối trên là **lược bỏ output để đọc cấu trúc**; đây không phải bản dump nguyên văn đầy đủ và không dùng làm test golden text. Hãy tự chạy `javap -v` để xem index, descriptor và static argument thực tế của build bạn đang dùng.

### 5.1. LambdaMetafactory làm gì trong bản build quan sát?

Khi `javac` chọn chiến lược liên kết lambda qua `invokedynamic`, bootstrap thường là `java.lang.invoke.LambdaMetafactory.metafactory` hoặc một biến thể như `altMetafactory`. Nó nhận các thông tin liên kết: caller lookup, tên/kiểu invokedynamic site, kiểu SAM và implementation method handle; từ đó tạo call site có khả năng sản sinh functional object phù hợp.

Nên phân biệt:

~~~text
invokedynamic ở vị trí TẠO lambda
    -> Bootstrap LambdaMetafactory
    -> phương án tạo functional object

invokeinterface IntUnaryOperator.applyAsInt ở vị trí GỌI lambda
    -> thực thi SAM thông qua object đã tạo
~~~

Thấy `invokedynamic` trong factory site **không có nghĩa mỗi lần `applyAsInt` đều phát lệnh `invokedynamic` tại vị trí gọi.** Trong bytecode mẫu, `applyAsInt` xuất hiện bằng `invokeinterface` khi người dùng sử dụng object.

`LambdaMetafactory` là API/cơ chế chuẩn của JDK, rất quan trọng để hiểu javac hiện đại. Tuy nhiên, hợp đồng **lambda ở Java source** không đòi chương trình được biên dịch phải có đúng một entry `LambdaMetafactory.metafactory`, cũng không đòi một runtime class có tên ổn định.

### 5.2. StringConcatFactory làm gì trong bản build quan sát?

Method:

~~~java
// Fragment từ chương trình:
static String format(String name, int count) {
    return "item=" + name + ", count=" + count;
}
~~~

được một bản `javac --release 17` hạ thành:

~~~text
static java.lang.String format(java.lang.String, int);
  Code:
     0: aload_0
     1: iload_1
     2: invokedynamic #26,  0  // InvokeDynamic #2:makeConcatWithConstants:(Ljava/lang/String;I)Ljava/lang/String;
     7: areturn
~~~

Ở đây `aload_0` đưa `name`, `iload_1` đưa `count` lên operand stack; instruction `invokedynamic` có signature nhận `(String,int)` và trả `String`.

Tên `makeConcatWithConstants` nói rằng bootstrap có thể nhận **recipe** kết hợp các phần cố định và placeholder cho operand runtime. Recipe có thể chứa các ký tự đánh dấu chuyên dụng như `\\u0001` (đối số runtime) và `\\u0002` (hằng bootstrap). Đây là **giao thức của StringConcatFactory**, không phải cú pháp String source hoặc ký tự chương trình tự in ra.

Một số trường hợp có thể dùng `StringConcatFactory.makeConcat` hoặc cách khác, tùy cách compiler hạ source. Đừng lấy `makeConcatWithConstants` làm quy tắc bắt buộc của toán tử `+` trong mọi compiler.

### 5.3. Hai invokedynamic khác mục đích

| Khía cạnh | Lambda factory site | String concat site |
| --- | --- | --- |
| Source điển hình | `n -> n * 2`, `Type::method` | `"item=" + name + count` |
| Hành vi quan sát | Tạo functional value có target type | Tạo giá trị String đã nối |
| Bootstrap mẫu từ javac | `LambdaMetafactory.metafactory` | `StringConcatFactory.makeConcatWithConstants` |
| Descriptor mẫu | `()IntUnaryOperator` hoặc `(int)IntUnaryOperator` khi capture | `(String,int)String` |
| Được JLS bảo đảm chính xác tên bootstrap? | **Không** | **Không** |
| Có thể quan sát bằng javap? | **Có**, ở classfile có dạng đó | **Có**, ở classfile có dạng đó |

Điểm chung là cách liên kết động của JVM thông qua instruction `invokedynamic`; điểm khác là loại kết quả và mục đích ngôn ngữ. Không đánh đồng “lambda là StringConcatFactory” chỉ vì cả hai đều có cùng opcode.

## 6. Điều JLS thực sự bảo đảm cho lambda và method reference

### 6.1. Functional interface và target typing

Một lambda như `x -> x + 1` **không có một kiểu object tùy ý độc lập với ngữ cảnh**: Java dùng *target typing* để xác định interface có đúng một abstract method chức năng (functional interface). Ví dụ:

~~~java
// Fragment, cần import java.util.function.IntUnaryOperator.
IntUnaryOperator inc = x -> x + 1;
int answer = inc.applyAsInt(6); // 7
~~~

Hợp đồng là có thể dùng `inc` như `IntUnaryOperator` với SAM `applyAsInt(int)`; không có hợp đồng rằng compiler phải sinh một method private tên `lambda$...` với exact descriptor nào đó.

### 6.2. Capture local phải effectively final

Trong `makeAdder`, parameter `step` không bị gán lại sau khi được nhận, nên hợp lệ để lambda capture.

~~~java
// Fragment hợp lệ:
int step = 5;
IntUnaryOperator add = x -> x + step;
// step không bị gán lại.
~~~

Đoạn dưới **cố ý không biên dịch được**, chỉ để minh họa quy tắc:

~~~java
// Fragment SAI: local step không effectively final.
int step = 5;
IntUnaryOperator add = x -> x + step;
step = 6; // compiler từ chối việc lambda capture biến này
~~~

Khi cần state thay đổi, bạn phải lựa chọn mô hình state rõ ràng (ví dụ field của một object được capture), rồi xử lý concurrency phù hợp. Đừng suy rằng một lambda giữ “reference tới local stack slot có thể gán lại”; đó không phải semantics Java local capture.

### 6.3. Lambda object identity không phải hợp đồng nghiệp vụ

Hai lần đánh giá cùng lambda expression có thể tạo cùng hoặc khác object theo lựa chọn runtime/implementation. Vì vậy không xây cache logic trên:

~~~java
// Fragment không nên dùng để quyết định semantics:
boolean same = ((Supplier<String>) () -> "hello")
        == ((Supplier<String>) () -> "hello");
~~~

Hai lambda expressions riêng trong source càng không có nghĩa phải dùng cùng object; đối chiếu `==` chỉ nói về reference identity thực tế lúc chạy. Hãy dùng API functional interface hoặc khóa nghiệp vụ nếu cần xác định equivalence.

**Tương tự, tên runtime class của lambda** có thể thay đổi. Trong các JDK hiện đại, implementation có thể sử dụng hidden classes, và `getClass().getName()` không phải representation ổn định để serialize, whitelist hoặc kiểm tra compatibility.

### 6.4. Method reference không bắt buộc nhanh hơn lambda

`LambdaConcatObservation::shout` và `s -> LambdaConcatObservation.shout(s)` có thể cùng hành vi ở phạm vi phù hợp, nhưng cách javac kết nối implementation handle và cách JVM tối ưu không nhất thiết tương đương byte-for-byte. Không rút kết luận hiệu năng từ việc method reference trong build quan sát có hoặc không có một method `lambda$...`.

Hãy chọn cách viết rõ ý nghĩa, kiểm tra null/receiver ở những loại method reference có receiver, và dùng benchmark cho bottleneck thật.

## 7. Điều JLS bảo đảm cho toán tử nối chuỗi +

Trong Java, toán tử `+` có thể là cộng số hoặc nối chuỗi. Khi một operand có kiểu `String`, các toán hạng được chuyển đổi thành biểu diễn String cần thiết, và kết quả là phép nối theo quy tắc của ngôn ngữ.

### 7.1. Thứ tự và tính kết hợp

`+` kết hợp trái, nên:

~~~java
// Fragment độc lập về mặt biểu thức:
String first = 1 + 2 + "x"; // "3x": tính số 1+2 trước
String second = "x" + 1 + 2; // "x12": nối từ trái sang phải
~~~

Không dùng một mô hình “mọi phần tử được chuyển thành String rồi nối” cho trường hợp mà những phép cộng số xuất hiện trước toán hạng String. Việc đặt ngoặc và kiểu operand quyết định semantics.

### 7.2. Null và string conversion

Một tham chiếu null trong nối chuỗi được biểu diễn bằng bốn ký tự `null`:

~~~java
// Fragment:
String missing = null;
String result = "value=" + missing; // "value=null"
~~~

Không phải `NullPointerException` chỉ vì operand là null, dù phương thức tự gọi trên null (ví dụ `missing.toString()`) sẽ gây lỗi. Việc chuyển đổi các object tùy ý sang chuỗi có thể gọi `toString()` và chịu hành vi của implementation đó; không nên giả định các đối tượng bất biến hoặc toString không có side effects.

### 7.3. Thứ tự đánh giá operand vẫn là vấn đề

Java đánh giá các operand theo thứ tự quy định, kể cả khi compiler gom kết quả vào một invokedynamic concat site. Nếu operand có side effect, thứ tự gọi phải được giữ; không thể chỉ vì bytecode concat sử dụng một bootstrap mà tùy tiện đảo thứ tự method calls.

Chương trình thứ hai ở mục 8 cho thấy `text("left")` được thực thi trước `number("right",7)` và sau đó tạo chuỗi `left:7`.

### 7.4. Constant folding là trường hợp khác

`"ab" + "cd"` chỉ gồm các literal thuộc constant expression, nên compiler có thể biểu diễn trực tiếp giá trị `"abcd"`; với constant expression String, JLS quy định xử lý tại compile time. Trong `javap` của demo, ta nhìn thấy:

~~~text
ldc  #... // String abcd
~~~

Điều này **không chứng minh rằng các phép nối có operand runtime cũng phải được fold**. Khi dùng `name` và `count` là biến runtime, output vẫn phải đúng nhưng bytecode có thể dùng `StringConcatFactory`, `StringBuilder` hoặc chiến lược khác.

## 8. Ví dụ chạy được 2: thứ tự đánh giá, null và captured local

Lưu thành **EvaluationOrderDemo.java**:

~~~java
public class EvaluationOrderDemo {
    private static String text(String name) {
        System.out.println("eval=" + name);
        return name;
    }

    private static int number(String name, int value) {
        System.out.println("eval=" + name);
        return value;
    }

    static String combine() {
        return text("left") + ":" + number("right", 7);
    }

    public static void main(String[] args) {
        System.out.println("combined=" + combine());
        String constant = "Java" + "17";
        System.out.println("folded=" + constant);
        String nullable = null;
        System.out.println("null=" + ("item=" + nullable));
        int captured = 3;
        java.util.function.IntUnaryOperator multiply = n -> n * captured;
        System.out.println("captured=" + multiply.applyAsInt(4));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 EvaluationOrderDemo.java
java EvaluationOrderDemo
~~~

**Stdout chính xác**:

~~~text
eval=left
eval=right
combined=left:7
folded=Java17
null=item=null
captured=12
~~~

Giải thích:

1. Operand đầu gọi `text("left")`, gây dòng `eval=left`.
2. Operand cuối gọi `number("right",7)`, gây dòng `eval=right`.
3. Kết quả nối phải giữ giá trị `left:7`.
4. Constant expression `"Java" + "17"` cho `Java17`.
5. `nullable` là null nhưng nối chuỗi vẫn cho `item=null`.
6. `multiply` capture local `captured=3` (effectively final), nên `4*3=12`.

Có thể kiểm tra bytecode:

~~~bash
javap -c -p EvaluationOrderDemo
~~~

Quan sát có thể cho thấy `invokestatic text` trước `invokestatic number`, rồi `invokedynamic` cho concat, nhưng **không dùng số offset instruction làm assertion về ngữ nghĩa**. Assertion tốt hơn là các dòng stdout đã liệt kê: thứ tự và giá trị vẫn phải giữ.

## 9. Thử nghiệm đối chứng: javac --release 8 và --release 17

Để thấy khác biệt do **target release**, dùng cùng một source đơn giản và biên dịch **hai lần vào thư mục output khác nhau**, tránh overwrite classfile của nhau.

Lưu file **ConcatTargetCompare.java**:

~~~java
public class ConcatTargetCompare {
  static String format(String name, int count) {
    return "item=" + name + ", count=" + count;
  }
  public static void main(String[] args) {
    System.out.println(format("A", 3));
  }
}
~~~

Trên JDK đủ mới hỗ trợ hai target:

~~~bash
javac --release 8 -d out8 ConcatTargetCompare.java
javac --release 17 -d out17 ConcatTargetCompare.java

java -cp out8 ConcatTargetCompare
java -cp out17 ConcatTargetCompare

javap -c -classpath out8 ConcatTargetCompare
javap -c -classpath out17 ConcatTargetCompare
~~~

Nếu shell không tạo folder khi dùng `-d`, hãy tạo `out8` và `out17` trước khi chạy. Trên một số JDK rất mới, `--release 8` có thể hiện cảnh báo deprecation/obsolete options hoặc ngừng hỗ trợ; **đừng ghi cứng stderr như một hợp đồng**.

**Stdout của cả hai bản chạy**:

~~~text
item=A, count=3
~~~

Trong phép thử đối chứng với bản javac hiện có, `javap -c` cho output tiêu biểu:

| Bản build | Cách hạ phép nối trong method format |
| --- | --- |
| `--release 8` | `new java/lang/StringBuilder`, nhiều lần `append`, `toString` |
| `--release 17` | `invokedynamic` với tên liên kết `makeConcatWithConstants` |

Hai đoạn trích lược mang tính minh họa:

~~~text
# Ví dụ release 8 — lược bớt offset và constant pool index:
new           ... // class java/lang/StringBuilder
invokespecial ... // StringBuilder.<init>
...
invokevirtual ... // StringBuilder.append
...
invokevirtual ... // StringBuilder.toString
~~~

~~~text
# Ví dụ release 17 — lược bớt constant pool index:
aload_0
iload_1
invokedynamic ... // makeConcatWithConstants:(Ljava/lang/String;I)Ljava/lang/String;
areturn
~~~

**Kết luận đúng:** Một source có thể được javac hạ theo những chiến lược classfile khác nhau khi target release thay đổi, trong khi **nghĩa của biểu thức Java và output đều giống nhau**.

**Kết luận sai:** “Java 8 bắt buộc JVM luôn cấp phát StringBuilder”, “Java 17 chắc chắn không có object trung gian”, “StringConcatFactory luôn nhanh hơn StringBuilder trong mọi workload”. Đây là các giả định về runtime/JIT cần đo, không thể kết luận chỉ từ opcode.

### 9.1. Vì sao cách này tốt hơn so hai file .class không kiểm soát?

Nếu bạn chỉ biên dịch một lần rồi đổi JDK để chạy, classfile **vẫn là cùng file đã biên dịch**; bytecode không tự viết lại thành phiên bản mới. Nếu muốn so đầu ra javac, cần thực sự **recompile**.

Cũng không nên thay cả source, compiler, target, JVM và input trong một lần thử rồi quy mọi khác biệt cho `--release`. Ghi rõ từng biến và giữ phần còn lại giống nhau.

## 10. Bytecode descriptor và constant pool: đọc cái gì là có ích?

Khi xem `javap`, phân biệt:

- **Tên method source**: `makeAdder`, `format`, `shout`.
- **NameAndType** trong constant pool: tên symbolic của dynamic call site và descriptor.
- **Descriptor** kiểu JVM: ví dụ `(I)Ljava/util/function/IntUnaryOperator;` (factory nhận int capture) hoặc `(Ljava/lang/String;I)Ljava/lang/String;` (concat nhận String và int).
- **BootstrapMethods index**: tham chiếu tới bản ghi bootstrap với method handle và các static argument.
- **Synthetic method**: helper do compiler thêm để hiện thực source, không tự động là public API.
- **Opcode**: `invokedynamic`, `invokeinterface`, `invokevirtual`, `ldc`, `aload`, `iload`, `areturn`...

Bảng descriptor hữu ích:

| Ký hiệu | Nghĩa |
| --- | --- |
| `I` | Java `int` |
| `V` | `void` |
| `Z` | `boolean` |
| `Ljava/lang/String;` | Reference tới `java.lang.String` |
| `Ljava/util/function/IntUnaryOperator;` | Reference tới functional interface |
| `(I)I` | Nhận int, trả int |
| `(I)Ljava/util/function/IntUnaryOperator;` | Nhận int, trả functional object |
| `(Ljava/lang/String;I)Ljava/lang/String;` | Nhận String và int, trả String |

`javap -s -p LambdaConcatObservation` giúp quan sát descriptor nhanh mà không phải đọc toàn bộ constant pool.

**Cẩn thận về hai nơi có descriptor khác nhau:** Với một lambda capturing, descriptor của **factory invokedynamic** không phải descriptor của **SAM method**. SAM `IntUnaryOperator.applyAsInt` là `(I)I`; factory site có thể là `(I)IntUnaryOperator` vì nó nhận dữ liệu capture rồi tạo functional object.

## 11. Một invokedynamic instruction không tự mô tả toàn bộ semantics

Khi thấy instruction:

~~~text
invokedynamic #N, 0 // InvokeDynamic #M:...
~~~

hãy đọc tiếp để biết:

1. **Descriptor của call site**: input/output trên operand stack.
2. **Bootstrap method**: ai thiết lập liên kết? LambdaMetafactory, StringConcatFactory hay bootstrap tùy chỉnh?
3. **Static bootstrap arguments**: implementation method handle, SAM type, concat recipe/hằng... khi có.
4. **Vị trí caller**: method nào của class gọi invokedynamic? Tạo functional object hay tạo String?
5. **Kết quả runtime thực**: chương trình chạy đúng contract không?

Một instruction dùng opcode chung có thể được liên kết thành nhiều hành vi khác nhau. Ngoài lambda/string concat, JVM cho phép bootstrap tùy chỉnh ở những trường hợp bytecode thích hợp. Do đó, thấy `invokedynamic` **không đủ** để kết luận “đây là lambda” hay “đây là String concat”.

### 11.1. Bootstrap không nhất thiết chạy trên mỗi lời gọi

`invokedynamic` có bước **linking** với bootstrap method. Sau khi một call site được liên kết thành công, những lần gọi lặp lại sử dụng linkage đó theo quy tắc JVM. Với runtime tối ưu, chi phí thực tế phụ thuộc nhiều yếu tố, nhưng đừng mô tả như “mỗi lần concat đều gọi `StringConcatFactory.makeConcatWithConstants` như một function Java bình thường”.

Đây cũng là lý do không thể dùng riêng tên bootstrap trong `javap` để đo số lần tạo object, number of allocations hoặc thời gian warmup.

### 11.2. StringConcatFactory có phải một lời gọi Java trong source?

Không. Source có toán tử `+`; compiler có thể chọn biểu diễn bằng bytecode `invokedynamic` và bootstrap StringConcatFactory. Người đọc `javap` thấy hậu quả của compilation, không phải source code đã trực tiếp gọi factory.

Đối với debugging/optimization, biết tên factory giúp điều tra cơ chế; đối với bảo đảm tương thích source, quan trọng là **giá trị String và thứ tự đánh giá đúng**.

## 12. Những khẳng định được phép và không được phép từ javap

| Quan sát | Có thể kết luận | Không được kết luận chỉ từ quan sát đó |
| --- | --- | --- |
| Thấy `invokedynamic` tại `makeAdder` | Classfile này có dynamic call site tại vị trí đó | Mọi compiler/version bắt buộc sinh cùng bytecode |
| Thấy `LambdaMetafactory.metafactory` | Bootstrap của classfile này tham chiếu LambdaMetafactory | Mỗi lần gọi SAM đều chạy bootstrap hoặc allocation |
| Thấy method `lambda$makeAdder$0` | Compiler này đã sinh helper method | Tên helper là API hoặc luôn tồn tại |
| Thấy `StringConcatFactory.makeConcatWithConstants` | Compiler này liên kết concat theo factory đó | Mọi phép `+` đều dùng factory; không có object trung gian |
| Thấy `new StringBuilder` | Bytecode chứa instruction tạo builder | Runtime buộc cấp phát object builder sau JIT |
| Thấy `ldc "abcd"` | Classfile mang constant `"abcd"` | Mọi String concat, kể cả operand runtime, đều fold được |
| Hai bản javac cho cùng stdout | Hành vi cụ thể của input thử nghiệm giống nhau | Mọi semantics/edge case đều đã được kiểm chứng |
| `javap -p` in private helper | Có member trong classfile | Nó là method source do người viết khai báo |
| Có một `invokedynamic` site | Có instruction với dynamic linkage | Biết được số lượng lần bootstrap chạy trong mọi runtime từ mỗi lời gọi |

Bảng này là cách phòng tránh lỗi “thấy một output bytecode, nâng nó thành quy tắc ngôn ngữ”.

## 13. Quy trình kiểm chứng thực tế khi nghi ngờ một chi tiết javac

Một thí nghiệm tốt có thể lặp lại bằng người khác:

1. **Viết câu hỏi cụ thể.** Ví dụ “khi lambda capture một int, call site có descriptor gì?”, không chỉ “javap lambda trông ra sao?”.
2. **Tạo source tối thiểu có hai đường đối chiếu.** Dùng một lambda capturing và một non-capturing, hoặc concat với constant operands và concat với runtime operands.
3. **Ghi JDK và target release.** `javac -version`, `java -version`, `--release`.
4. **Biên dịch vào thư mục riêng.** Không để class cũ che khuất bản build mới.
5. **Chạy chương trình và kiểm stdout trước.** Đây là hành vi thực của bản test.
6. **Dùng `javap -c -p` xác định instruction.** Nếu là invokedynamic, đọc `javap -v -p` để tra `BootstrapMethods`.
7. **Đối chiếu JLS/JVMS.** Điều nào bắt buộc, điều nào được phép thay đổi?
8. **Chỉ so sánh một biến tại một thời điểm.** Ví dụ `--release 8` vs 17, giữ source và compiler giống nhau.
9. **Không khẳng định hiệu năng từ bytecode.** Khi cần tối ưu, dùng profiler hoặc benchmark như JMH với warm-up, có kế hoạch tránh dead-code elimination.
10. **Viết kết luận có phạm vi.** “Trong thử nghiệm javac X, target 17, method format dùng invokedynamic...” khác “Java luôn dùng invokedynamic cho +”.

### 13.1. Khi bản build của bạn khác ví dụ

Nếu javap có thêm method, index khác hoặc concat dùng `makeConcat` thay vì `makeConcatWithConstants`, đừng vội xem như lỗi. Hãy kiểm tra rằng:

- Chương trình chạy cho output đúng.
- Class file thật sự là bản vừa build, đúng release.
- Output BootstrapMethods liên kết được với invokedynamic site.
- Các chi tiết khác biệt không vi phạm quy tắc ngôn ngữ.

Nếu class được compiler khác (ECJ, Kotlin compiler, Scala compiler...), một mô tả dành cho `javac` không nhất thiết áp dụng. Bài này không tuyên bố cách các compiler khác phải sinh bytecode.

## 14. Các lỗi phổ biến

### Lỗi 1 — Đọc LambdaMetafactory như method nghiệp vụ

LambdaMetafactory được dùng để liên kết **cách tạo functional object** trong một bản implementation. Nó không phải body lambda `x -> x + step`; body có thể nằm trong helper, method tham chiếu hoặc một target khác. Muốn hiểu kết quả, phải đọc implementation handle và code của body.

### Lỗi 2 — Kết luận lambda có class cố định

Tên runtime lambda class, có thể có các dấu `$$Lambda` hoặc hidden-class behavior, không phải API ổn định. Không serialize bằng tên class đó, không bind Reflection vào synthetic names, không xây logic phụ thuộc `getClass().toString()` của lambda.

### Lỗi 3 — Nhầm captured input với SAM input

Factory `invokedynamic:(I)IntUnaryOperator` nhận `step` đã capture, còn `applyAsInt(int)` nhận `input` khi gọi sau. Đây là hai giai đoạn và hai interface chữ ký khác nhau.

### Lỗi 4 — Tưởng mọi String concat đều xuất hiện trong javap thành invokedynamic

Constant expressions có thể được compile thành `ldc` của String constant; target release 8 có thể dùng StringBuilder; compiler khác được phép chọn cách khác. `+` là syntax ngôn ngữ, không phải một opcode duy nhất.

### Lỗi 5 — Đồng nhất StringBuilder trong bytecode với allocation runtime

JIT có thể thực hiện escape analysis và các tối ưu khác. `javap` chỉ phản ánh classfile trước runtime optimization. Nếu cần con số allocation/throughput, phải đo ứng dụng thật.

### Lỗi 6 — So constant-pool index như số định danh vĩnh viễn

Số `#19`, `#26`, `#141` thay đổi khi compiler thêm/bớt constant hoặc thứ tự phát sinh. Khi làm test bytecode, chuẩn hóa/khớp **cấu trúc có ý nghĩa** thay vì hardcode index.

### Lỗi 7 — Dùng output javap làm bằng chứng source hợp lệ về mặt JLS

Bytecode thậm chí có thể được sinh bởi tool khác, không phải Java source. Một classfile hợp lệ không chứng minh rằng source tương ứng có thể viết và biên dịch bằng `javac` với đúng cú pháp Java.

### Lỗi 8 — Bỏ qua String conversion của null và operand có side effects

Dù compiler dùng invokedynamic, biểu thức `"x=" + nullReference` phải cho String mang `null`; các operand có side effects phải được đánh giá đúng quy tắc. Không đổi source theo “tối ưu” mà làm thay đổi thứ tự gọi method.

### Lỗi 9 — Tưởng --release 17 đồng nghĩa đang chạy javac 17

Một `javac` mới có thể target classfile Java 17. Cách hạ bytecode của bản javac mới chưa chắc giống từng dòng so với `javac 17`. Ghi cả `javac -version` và `--release`.

### Lỗi 10 — Nhìn javap mà bỏ qua BootstrapMethods

Dòng `invokedynamic` và name/descriptor của nó không đủ để xác định toàn bộ cơ chế. Dùng `-v` để nối constant-pool entry, bootstrap method handle và arguments.

## 15. Tự kiểm tra có đáp án

**Câu 1.** `javap -c` thấy `invokedynamic` tại `makeAdder(int step)` với descriptor `(I)IntUnaryOperator`. Chữ `I` biểu diễn gì?

**Đáp án:** Dữ liệu `int step` cần capture **khi tạo functional object**, không phải `input` của `applyAsInt(int)` khi gọi sau.

**Câu 2.** `javap` thấy private method `lambda$makeDoubler$0`. Có thể xem đó là method API nên gọi bằng Reflection không?

**Đáp án:** Không. Đây là helper do bản `javac` hiện tại sinh ra, có thể thay tên hoặc không tồn tại ở compiler khác.

**Câu 3.** `"ab" + "cd"` có nhất thiết tạo `StringBuilder` ở runtime không?

**Đáp án:** Không. Đây là constant expression; javac thử nghiệm phát hành `ldc` của `"abcd"`. Ngay cả bytecode dùng builder trong trường hợp khác cũng không chứng minh JIT phải cấp phát object.

**Câu 4.** `"x" + 1 + 2` và `1 + 2 + "x"` có giống nhau không?

**Đáp án:** Không. `"x12"` so với `"3x"`, vì `+` kết hợp trái và kiểu toán hạng quyết định phép cộng hay phép nối.

**Câu 5.** Thấy `StringConcatFactory.makeConcatWithConstants` trong BootstrapMethods có nghĩa mỗi lần gọi format đều chạy factory từ đầu không?

**Đáp án:** Không. Bootstrap tham gia bước liên kết dynamic call site; những lời gọi sau dùng linkage đã thiết lập theo quy tắc JVM, không nhất thiết gọi lại factory.

**Câu 6.** Cùng source `format`, `--release 8` dùng StringBuilder còn `--release 17` dùng invokedynamic. Điều gì cần vẫn đúng?

**Đáp án:** Kết quả String và các semantics của toán tử `+` theo JLS. Cách phát sinh classfile có thể khác.

**Câu 7.** Có thể suy ra `makeDoubler() == makeDoubler()` luôn true vì lambda không capture gì không?

**Đáp án:** Không. Identity của functional object không phải semantics nghiệp vụ được JLS bảo đảm. Implementation có thể tái sử dụng hoặc tạo object.

**Câu 8.** Vì sao `javap -v` quan trọng hơn `javap -c` khi nghiên cứu invokedynamic?

**Đáp án:** Nó cho thấy constant pool và `BootstrapMethods`, giúp truy từ invokedynamic site tới bootstrap handle và static arguments. `-c` chủ yếu cho instruction.

**Câu 9.** Muốn đo allocation của nối chuỗi, chỉ nhìn `new StringBuilder` trong `javap` có đủ không?

**Đáp án:** Không. Cần đo runtime có JIT với profiler/benchmark thích hợp; bytecode không chứng minh allocation thực sự xảy ra sau tối ưu.

**Câu 10.** Làm thế nào phân biệt điều được Java bảo đảm với một chi tiết build ngẫu nhiên?

**Đáp án:** Lấy JLS/JVMS làm căn cứ cho semantics và classfile format, dùng javap để ghi nhận một output cụ thể của compiler, rồi tránh biến số index, helper names hoặc concat strategy thành API contract.

## Ghi nhớ cuối bài

- **`javap` cho biết compiler đã emit gì, không phải tất cả những gì JLS bắt buộc.**
- Lambda/method reference là **giá trị functional interface**; một bản javac hiện đại có thể dùng `invokedynamic` và `LambdaMetafactory`, song helper name/runtime identity không ổn định.
- Nối chuỗi `+` được định nghĩa bởi **semantics của ngôn ngữ**; một bản build có thể dùng `StringConcatFactory`, bản khác dùng `StringBuilder`, hoặc constant-fold ngay trong classfile.
- Khi xem `invokedynamic`, đọc đủ **descriptor + constant pool + BootstrapMethods**.
- **Capture lúc tạo lambda** khác với **tham số SAM lúc gọi lambda**.
- Mọi kết luận nên ghi rõ **JDK, `--release`, source, classfile**; muốn kết luận hiệu năng phải đo runtime, không chỉ xem disassembly.

## Tài liệu tham khảo

- Java Language Specification, Java SE 17, **Lambda Expressions** (§15.27): https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.27
- Java Language Specification, Java SE 17, **Method References** (§15.13): https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.13
- Java Language Specification, Java SE 17, **Additive Operators / String Concatenation** (§15.18): https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.18
- Java Language Specification, Java SE 17, **Constant Expressions** (§15.29): https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.29
- Java Virtual Machine Specification, Java SE 17, **invokedynamic** (§6.5): https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html#jvms-6.5.invokedynamic
- Java SE 17, **LambdaMetafactory**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/LambdaMetafactory.html
- Java SE 17, **StringConcatFactory**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/StringConcatFactory.html
- JDK Tool Specs, **javap**: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html
- JDK Tool Specs, **javac**: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html
