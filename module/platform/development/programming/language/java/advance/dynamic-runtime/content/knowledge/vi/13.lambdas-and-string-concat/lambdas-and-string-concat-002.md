# 13.2 Ba giai đoạn liên kết, giữ biến được bắt và thực thi của `LambdaMetafactory`

Một biểu thức lambda của Java trông rất ngắn, chẳng hạn `x -> base + x`, nhưng runtime phải giải quyết ba câu hỏi khác nhau: **làm thế nào tạo ra một đối tượng triển khai functional interface**, **đối tượng đó giữ những giá trị nào từ môi trường tạo lambda**, và **điều gì xảy ra khi gọi phương thức của đối tượng**. Tài liệu Java SE 17 về `java.lang.invoke.LambdaMetafactory` gọi ba giai đoạn này là:

1. **Linkage (liên kết):** chọn cách hiện thực functional interface và tạo một `CallSite` có target hoạt động như **factory tạo function object**.
2. **Capture (giữ biến được bắt):** gọi target của `CallSite` với các giá trị môi trường hiện tại; nhận về đối tượng triển khai interface và mang theo các giá trị cần thiết.
3. **Invocation (thực thi):** gọi **phương thức trừu tượng (SAM)** trên function object; lúc này method hiện thực nhận cả các giá trị đã capture và các đối số mới của lời gọi.

Đây là ba mốc logic **khác nhau**, không phải ba tên của cùng một thao tác. Một điểm gọi `invokedynamic` có thể được liên kết một lần, được thực thi để tạo function object nhiều lần, và mỗi function object có thể tiếp tục được gọi nhiều lần.

Bài dùng **Java 17+**, `LambdaMetafactory`, `MethodHandle`, `CallSite` và ví dụ lambda/method reference do `javac` biên dịch.

## 1. Một ví dụ xuyên suốt: `base` là captured argument, `x` là invocation argument

Xét method:

~~~java
static java.util.function.IntUnaryOperator makeAdder(int base) {
    return x -> base + x;
}
~~~

Đây là một method **minh họa**, không phải file Java độc lập. `IntUnaryOperator` là functional interface có đúng một phương thức trừu tượng:

~~~java
int applyAsInt(int operand);
~~~

Đọc từng giá trị:

- `base` có sẵn khi chương trình **đánh giá biểu thức lambda** trong `makeAdder(base)`. Lambda **capture giá trị** `base`.
- `x` chưa tồn tại ở thời điểm tạo function object; nó chỉ xuất hiện khi caller gọi `function.applyAsInt(x)`.
- Phép cộng `base + x` thuộc **invocation**, không diễn ra khi chỉ mới tạo function object.

Ví dụ ý nghĩa:

~~~text
makeAdder(10)  -> function object giữ base=10
makeAdder(20)  -> function object giữ base=20

function10.applyAsInt(2)  -> 10 + 2 -> 12
function10.applyAsInt(4)  -> 10 + 4 -> 14
function20.applyAsInt(2)  -> 20 + 2 -> 22
~~~

Mặc dù gọi `makeAdder` nhiều lần, mã bytecode cho cùng biểu thức lambda có thể chứa **một vị trí `invokedynamic`**. Linkage thuộc về vị trí bytecode ấy, còn các giá trị `10`, `20` xuất hiện ở những lần **capture** khác nhau. Không đánh đồng số lần tạo/nhận function object với số lần bootstrap được chạy.

## 2. Sơ đồ ba giai đoạn và hai nguồn đối số

~~~text
                CLASS FILE / BOOTSTRAP METADATA
            (SAM type, implementation handle,
             instantiated SAM type, call-site type)
                              │
                              ▼
   ┌────────────────────────────────────────────────────┐
   │ 1. LINKAGE: LambdaMetafactory.metafactory(...)    │
   │    -> CallSite được chọn cho invokedynamic        │
   │    -> target của site là FACTORY                  │
   └────────────────────────────────────────────────────┘
                              │
                      factory có kiểu:
                   (int)IntUnaryOperator
                              │
             ┌────────────────┴────────────────┐
             ▼                                 ▼
   ┌─────────────────────┐          ┌─────────────────────┐
   │ 2. CAPTURE: base=10 │          │ 2. CAPTURE: base=20 │
   │ factory.invoke(10)  │          │ factory.invoke(20)  │
   │ -> function A       │          │ -> function B       │
   └─────────────────────┘          └─────────────────────┘
             │                                 │
       function A giữ 10                 function B giữ 20
             │                                 │
             ▼                                 ▼
   ┌─────────────────────┐          ┌─────────────────────┐
   │ 3. INVOCATION       │          │ 3. INVOCATION       │
   │ A.applyAsInt(2)     │          │ B.applyAsInt(2)     │
   │ impl(10,2) -> 12    │          │ impl(20,2) -> 22    │
   └─────────────────────┘          └─────────────────────┘
~~~

Trong sơ đồ, function A/B biểu thị **hành vi và các giá trị capture**. JVM **không cam kết** luôn cấp phát một instance mới trong mỗi lần capture. Đừng suy ra `functionA != functionB` chỉ từ việc biểu thức lambda được đánh giá hai lần.

Có hai danh sách đối số độc lập:

| Danh sách | Xuất hiện khi nào? | Ví dụ |
| --- | --- | --- |
| **Static/bootstrap arguments** | Lưu trong metadata của class file, được dùng để liên kết | `samMethodType`, `implMethod`, `instantiatedMethodType` |
| **Dynamic/captured arguments** | Trên operand stack khi chạy factory target tại `invokedynamic` | Giá trị `base=10` hoặc `base=20` |
| **Invocation arguments** | Khi caller gọi SAM trên function object | Giá trị `x=2`, `x=4` |

**Không** đưa giá trị `base=10` vào danh sách static arguments của bootstrap cho ví dụ `makeAdder`. BSM cần biết **kiểu và số lượng** biến sẽ capture, không biết trước **giá trị từng lần**.

## 3. Giai đoạn 1 — Linkage: từ metadata đến `CallSite`

Trên Java 17, `javac` thường hạ một biểu thức lambda/method reference thành chỉ thị `invokedynamic`. Class file có:

- Entry `CONSTANT_InvokeDynamic_info` mang **tên phương thức interface cần hiện thực** (thường là tên SAM như `applyAsInt`) và **call-site descriptor**.
- Entry tương ứng trong thuộc tính `BootstrapMethods`, tham chiếu BSM như `LambdaMetafactory.metafactory` và các static arguments.
- Một implementation method được biểu diễn bằng **direct `MethodHandle`**. Với lambda chứa body, compiler có thể tạo method tổng hợp tên dạng `lambda$...` trong class chứa biểu thức. Với method reference, handle có thể trỏ trực tiếp tới method/constructor đích.

BSM thường có dạng Java SE 17:

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

Tên tham số trong JavaDoc hiện hành tương ứng với nhiều ví dụ dùng `invokedType`/`samMethodType`/`implMethod`/`instantiatedMethodType`:

| Tham số | Nguồn/ý nghĩa |
| --- | --- |
| `caller` | `Lookup` đại diện **class chứa điểm gọi** và quyền truy cập cần thiết; khi JVM thực thi bootstrap sẽ cung cấp |
| `interfaceMethodName` | Tên SAM cần hiện thực, ví dụ `applyAsInt` |
| `factoryType` / `invokedType` | **Kiểu target của `CallSite`**, gồm danh sách kiểu của các captured arguments và **kiểu trả về là functional interface** |
| `interfaceMethodType` / `samMethodType` | Kiểu method SAM ở dạng được hiện thực, ví dụ `(int)int` |
| `implementation` / `implMethod` | Direct handle tới method thực hiện nghiệp vụ, ví dụ `(int,int)int` |
| `dynamicMethodType` / `instantiatedMethodType` | Kiểu thực hóa dùng kiểm tra/chuyển đổi khi **gọi SAM**; có thể khác erased SAM type do generic specialization |

**Ba đối số đầu** được JVM chuẩn bị từ ngữ cảnh của `invokedynamic`. Ba đối số tiếp theo thường là các static bootstrap arguments ghi trong class file. Chúng mô tả hình dạng function; **không phải** ba đối số của mỗi lần gọi lambda.

Với `makeAdder(int base)`, ta có mô hình kiểu:

~~~text
factoryType / invokedType:       (int)IntUnaryOperator
interfaceMethodType / SAM type:  (int)int
implementation MethodHandle:    (int,int)int
dynamic/instantiated SAM type:   (int)int

Captured parameter count K = 1  (base)
SAM parameter count      N = 1  (x)
Implementation arity     M = 2  (base, x)
                       K + N = M
~~~

`(int)IntUnaryOperator` thuộc về **factory**, còn `(int)int` thuộc về **hàm được gọi sau**. Đây là điểm nhầm phổ biến nhất khi đọc `javap`.

### 3.1. Hợp đồng kiểu tại linkage

`LambdaMetafactory` kiểm tra nhiều điều kiện, trong đó có:

- Kiểu trả về của `factoryType` phải là interface có thể được tạo function object phù hợp.
- `implementation` phải là **direct MethodHandle** hợp lệ tới method hoặc constructor, không tùy tiện là một chuỗi adapter bất kỳ.
- Với dạng chuẩn, số tham số của implementation bằng số captured arguments cộng số đối số SAM: **`K + N = M`**.
- Các kiểu captured parameters phải khớp với các tham số tương ứng ở đầu implementation; các kiểu SAM, kiểu instantiated và kết quả phải thỏa các quy tắc thích nghi của metafactory.
- `caller` phải có ngữ cảnh lookup đủ quyền theo hợp đồng API.

Không dùng quy tắc chuyển đổi Java một cách tùy tiện để “chữa” mọi mismatch. Cấu trúc trái quy định có thể ném `LambdaConversionException` khi gọi metafactory, hoặc gây lỗi liên kết nếu JVM đang gọi metafactory như một bootstrap.

### 3.2. JVM chọn site và ghi nhớ linkage

Khi JVM dùng bootstrap cho **một chỉ thị `invokedynamic` cụ thể**, nó chấp nhận một `CallSite` có kiểu phù hợp descriptor và gắn site đã chọn vào chỉ thị. Sau đó chạy factory target của site, chứ **không gọi lại metafactory cho từng function object**.

Trong trường hợp nhiều thread cùng đến một chỉ thị unlinked, các bootstrap attempt có thể cạnh tranh, và JVM chọn một kết quả để liên kết. Do đó đừng dựa vào việc có đúng **một lần thực thi vật lý** của BSM để làm side effect duy nhất. Ngay cả khi JVM tối ưu theo cách khác, hành vi quan sát được phải phù hợp quy tắc linkage.

`LambdaMetafactory` có thể tạo/tải class hiện thực, có thể sử dụng hidden class hoặc cơ chế JVM phù hợp. **Không phụ thuộc** vào tên lớp, tên package, số lượng class sinh ra hay thứ tự cấp phát của function object.

## 4. Giai đoạn 2 — Capture: factory nhận các giá trị môi trường

Sau liên kết, `CallSite.getTarget()` là một `MethodHandle` đóng vai trò **factory**. Trong ví dụ:

~~~text
factory.type() == (int)IntUnaryOperator
~~~

Khi thực thi `factory(base)`, runtime lấy giá trị `base` ở **lần đánh giá biểu thức lambda hiện tại** và trả về một `IntUnaryOperator` có thể dùng về sau.

Tại thời điểm capture:

- Các đối số được chuyển cho factory là **captured values**, không phải các đối số của `IntUnaryOperator.applyAsInt`.
- Giá trị primitive như `int base` được giữ theo giá trị. Khi caller sau này đưa `x` mới, base đã capture vẫn giữ giá trị tương ứng lần tạo.
- Nếu capture là **tham chiếu object**, function giữ một tham chiếu đến **cùng object**, không sao chép sâu trạng thái object. Mutation hợp lệ trên object có thể được quan sát sau đó.
- Việc capture **không chạy nghiệp vụ trong lambda body**. Với `x -> base + x`, phép cộng chỉ thực thi khi `applyAsInt(x)` được gọi.
- Function object tạo tại capture có thể là object mới hoặc object có sẵn. Identity không phải hợp đồng ổn định; không dùng `==`, `System.identityHashCode` hoặc intrinsic lock trên lambda object làm cơ sở cho logic nghiệp vụ.

### 4.1. “Biến được bắt” và effectively final

Trong Java, **local variable hoặc parameter được lambda truy cập phải final hoặc effectively final**. Ví dụ hợp lệ:

~~~java
int base = 10;
java.util.function.IntUnaryOperator op = x -> base + x;
// Không gán lại base sau khi nó được lambda sử dụng.
~~~

Đây là **mã minh họa trong phạm vi method**, không phải file độc lập. Nếu thêm `base = 11;` trong cùng phạm vi sau khi lambda tham chiếu `base`, compiler báo lỗi vì `base` không còn effectively final.

Điều kiện effectively final liên quan đến **biến local/parameter**, không có nghĩa đối tượng được tham chiếu là immutable. Ví dụ:

~~~java
java.util.concurrent.atomic.AtomicInteger box =
        new java.util.concurrent.atomic.AtomicInteger(5);
java.util.function.IntSupplier read = box::get;
System.out.println(read.getAsInt()); // 5
box.set(8);
System.out.println(read.getAsInt()); // 8
~~~

Ở đây lambda/method reference giữ **tham chiếu `box`**, còn `box` tự thay đổi state. `AtomicInteger` giúp ví dụ rõ ràng; với object mutable thông thường, việc chia sẻ giữa nhiều thread vẫn cần quy tắc đồng bộ phù hợp.

### 4.2. Captured receiver trong method reference

Trong biểu thức `box::get`, receiver `box` được lấy ở thời điểm **đánh giá method reference**. Sau đó gọi `IntSupplier.getAsInt()` sử dụng cùng receiver ấy. Vì không có đối số SAM, kiểu implementation handle có thể hình dung như:

~~~text
captured receiver:  AtomicInteger box
SAM arguments:      (none)
implementation:     AtomicInteger.get() -> int
factory:            (AtomicInteger)IntSupplier
SAM:                ()int
~~~

Với **bound instance method reference** (như `box::get`), receiver null thường bị từ chối ngay khi đánh giá method reference theo quy tắc Java, thay vì chờ đến lần gọi SAM. Với `x -> x.method()`, `x` là **đối số SAM**, không phải captured receiver; lỗi null nếu có thường phát sinh lúc invocation.

### 4.3. Capture không đồng nghĩa luôn tạo object mới

Một lambda **không capture gì**, như `() -> 42`, có factory type `()Supplier`: không cần dữ liệu từ môi trường. JVM được phép tái sử dụng function object giữa các lần đánh giá. Ngay cả với capture, API cũng không cam kết identity theo cách đơn giản là “mỗi lần một object”.

Nếu cần **trạng thái identity riêng** hoặc lifecycle rõ ràng cho mỗi request, hãy tự tạo class/object có contract identity ổn định, thay vì giả định tính duy nhất của lambda object.

## 5. Giai đoạn 3 — Invocation: gọi SAM mới chạy phần việc

Sau khi đã có function object:

~~~java
int value = op.applyAsInt(2);
~~~

Đây là lời gọi **phương thức SAM** trên đối tượng `op`. Với `IntUnaryOperator`, SAM là `applyAsInt(int)int`. Lambda/metafactory bảo đảm method hiện thực sẽ gọi hành vi của `implementation MethodHandle` với hai nhóm giá trị:

~~~text
arguments to implementation =
    captured arguments (đã giữ tại capture)
    + invocation arguments (được truyền khi gọi SAM)

Ví dụ:
  captured base = 10
  invocation x  = 2
  implementation(base, x) -> 12
~~~

Một function object có thể được gọi nhiều lần với các input khác nhau:

~~~text
capture một lần: base=10
  ├─ applyAsInt(2) -> 12
  ├─ applyAsInt(4) -> 14
  └─ applyAsInt(9) -> 19
~~~

Không chạy lại BSM, và cũng không cần “capture lại” base cho mỗi lời gọi `applyAsInt`.

Trong Java bytecode, `invokedynamic` của `makeAdder` tạo **function object**; gọi `op.applyAsInt(...)` từ biến có kiểu `IntUnaryOperator` thường là `invokeinterface`. Hai chỉ thị này đảm nhận **hai vai trò khác nhau**. Bỏ qua sự phân biệt này dễ khiến người đọc tưởng mỗi lần thực thi lambda body sẽ kích hoạt bootstrap.

## 6. Chương trình Java 17 hoàn chỉnh: tự tạo metafactory và quan sát ba pha

Chương trình sau có **hai phần khác nhau có chủ đích**:

1. Gọi **trực tiếp** `LambdaMetafactory.metafactory` bằng Java để bạn thấy rõ `CallSite`, kiểu factory và thời điểm capture/invocation. Phần gọi trực tiếp này **không tự sinh một chỉ thị `invokedynamic` liên kết vào bootstrap**.
2. Khai báo một lambda thật `input -> base + input` và method reference `box::get` để `javac --release 17` phát ra `invokedynamic` trong bytecode. Xem bằng `javap` ở phần tiếp.

Tạo file **`LambdaLifecycleDemo.java`**:

~~~java
import java.lang.invoke.CallSite;
import java.lang.invoke.LambdaMetafactory;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.IntSupplier;
import java.util.function.IntUnaryOperator;

public final class LambdaLifecycleDemo {
    private static int implementation(int captured, int input) {
        System.out.println("  implementation(captured=" + captured + ", input=" + input + ")");
        return captured + input;
    }

    static IntUnaryOperator compiledLambda(int base) {
        return input -> base + input;
    }

    static IntSupplier referenceCapture(AtomicInteger box) {
        return box::get;
    }

    public static void main(String[] args) throws Throwable {
        System.out.println("phase 1: linkage");
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodHandle impl = lookup.findStatic(
                LambdaLifecycleDemo.class,
                "implementation",
                MethodType.methodType(int.class, int.class, int.class));
        CallSite site = LambdaMetafactory.metafactory(
                lookup,
                "applyAsInt",
                MethodType.methodType(IntUnaryOperator.class, int.class),
                MethodType.methodType(int.class, int.class),
                impl,
                MethodType.methodType(int.class, int.class));
        System.out.println("factory type: " + site.type());

        System.out.println("phase 2: capture");
        MethodHandle factory = site.getTarget();
        IntUnaryOperator add10 = (IntUnaryOperator) factory.invokeExact(10);
        IntUnaryOperator add20 = (IntUnaryOperator) factory.invokeExact(20);

        System.out.println("phase 3: invocation");
        System.out.println("add10(2): " + add10.applyAsInt(2));
        System.out.println("add10(4): " + add10.applyAsInt(4));
        System.out.println("add20(2): " + add20.applyAsInt(2));

        IntUnaryOperator compiled = compiledLambda(7);
        System.out.println("javac lambda(3): " + compiled.applyAsInt(3));

        AtomicInteger box = new AtomicInteger(5);
        IntSupplier reader = referenceCapture(box);
        System.out.println("reference before: " + reader.getAsInt());
        box.set(8);
        System.out.println("reference after: " + reader.getAsInt());
    }
}
~~~

Biên dịch/chạy từ thư mục chứa file:

~~~bash
javac --release 17 LambdaLifecycleDemo.java
java LambdaLifecycleDemo
~~~

**Stdout chính xác (đã kiểm tra với OpenJDK 21, mã nguồn biên dịch ở mức Java 17):**

~~~text
phase 1: linkage
factory type: (int)IntUnaryOperator
phase 2: capture
phase 3: invocation
  implementation(captured=10, input=2)
add10(2): 12
  implementation(captured=10, input=4)
add10(4): 14
  implementation(captured=20, input=2)
add20(2): 22
javac lambda(3): 10
reference before: 5
reference after: 8
~~~

Cách đọc kết quả:

- `phase 1: linkage` xuất hiện trước factory type: lời gọi metafactory đã **tạo `CallSite`**, có target mang kiểu `(int)IntUnaryOperator`.
- Ở `phase 2: capture`, gọi cùng factory hai lần với `10` và `20` để nhận hai function value có hành vi tương ứng. Chưa thấy dòng `implementation(...)` nào; đó là vì body **chưa chạy**.
- Dòng `implementation(captured=10, input=2)` chỉ xuất hiện **sau** `phase 3: invocation` khi gọi `add10.applyAsInt(2)`. Lúc ấy implementation nhận cả captured value `10` lẫn invocation argument `2`.
- `add10` được gọi thêm với input `4` mà captured value vẫn là `10`. `add20` cho kết quả khác vì nó được tạo với captured value `20`.
- `compiledLambda(7)` minh họa cùng hành vi nhưng **do compiler tạo invokedynamic tự động**, không thông qua lời gọi `metafactory` viết tay trong `main`.
- `reference before/after` cho thấy function giữ tham chiếu đến cùng `AtomicInteger` và có thể quan sát state cập nhật.

**Không** suy ra rằng mã `main` “BSM của lambda compiler đã chạy đúng một lần”: logging ở ba giai đoạn là do chương trình tự in khi **gọi trực tiếp metafactory**. Chỉ phần `compiledLambda`/`referenceCapture` thực sự dùng bytecode `invokedynamic` do `javac` tạo.

## 7. Đọc `javap` để nối kiến thức Java source với bytecode

Sau khi biên dịch file trên, chạy:

~~~bash
javap -c -p LambdaLifecycleDemo
javap -v -p LambdaLifecycleDemo
~~~

Tìm riêng method `compiledLambda` trong đầu ra `javap -c -p`. Cấu trúc quan sát được khi biên dịch Java 17 là:

~~~text
static java.util.function.IntUnaryOperator compiledLambda(int);
  Code:
     0: iload_0
     1: invokedynamic ... // applyAsInt:(I)Ljava/util/function/IntUnaryOperator;
     6: areturn
~~~

Phần `...` thay thế **constant-pool index và metadata hiển thị cụ thể**, có thể khác giữa các bản `javac`; đây không phải yêu cầu đối chiếu byte-for-byte toàn bộ stdout của `javap`.

Hãy nối ba dòng bytecode với vòng đời:

- `iload_0` đặt **giá trị `base`** lên operand stack.
- `invokedynamic ... applyAsInt:(I)L...IntUnaryOperator;` là **factory call site**: nhận một `int` (giá trị capture) và trả một `IntUnaryOperator`.
- `areturn` trả function object cho caller. Chưa có lời gọi `applyAsInt` trong method này.

Trong `javap -v -p`, xem `Constant pool` và `BootstrapMethods`. Với compiler Java 17 trong ví dụ, entry cho `compiledLambda` tham chiếu tới `LambdaMetafactory.metafactory` với ba static arguments mang ý nghĩa:

~~~text
SAM method type:         (I)I
Implementation handle:   REF_invokeStatic
                         LambdaLifecycleDemo.lambda$compiledLambda$...(II)I
Instantiated method type:(I)I
~~~

`lambda$compiledLambda$...` là tên minh họa của một method tổng hợp do compiler tạo; phần suffix/index **không phải API ổn định**. Đặc biệt, BSM static args chứa **MethodHandle mô tả implementation**, **không** chứa giá trị `base=7` của lần chạy cụ thể.

Trong bytecode của `referenceCapture`, call-site descriptor có thể mang kiểu receiver:

~~~text
(AtomicInteger)IntSupplier
~~~

Method handle có thể trỏ tới `AtomicInteger.get()`. Receiver object được cung cấp trong **capture**; không phải một tham số của `IntSupplier.getAsInt()` khi invocation.

**Lưu ý khi dùng `javap`:** class ví dụ còn dùng phép nối chuỗi trong `System.out.println`, nên class file có thể chứa các bootstrap entry của **`StringConcatFactory`**. Đừng coi mọi `invokedynamic` trong class đều thuộc `LambdaMetafactory`: xem đúng tên bootstrap và điểm gọi cần nghiên cứu.

## 8. `samMethodType` khác `instantiatedMethodType` như thế nào?

Trong ví dụ `IntUnaryOperator` không dùng generic, cả hai đều là `(int)int`. Nhưng với functional interface generic, sự khác biệt rất hữu ích.

Ví dụ:

~~~java
java.util.function.Function<String, Integer> f =
        text -> text.length();
Integer n = f.apply("hello"); // 5
~~~

Đây là **đoạn Java minh họa trong method**, không phải chương trình chạy độc lập.

Sau **type erasure**, method `Function.apply` về mặt JVM có chữ ký tham chiếu `(Object)Object`. Khi compiler chuyên biệt lambda cho `Function<String,Integer>`, instantiated SAM type có thể là `(String)Integer` (mức boxing/kiểu hiện thực phụ thuộc cách compiler tạo implementation).

Do đó các giá trị metadata có vai trò riêng:

- **`samMethodType`:** mô tả chữ ký interface method sau erasure mà generated function object phải thực hiện, ví dụ `(Object)Object`.
- **`instantiatedMethodType`:** mô tả ràng buộc kiểu cần kiểm tra/chuyển đổi tại invocation, ví dụ `(String)Integer`.
- **`implMethod`:** method thực tế xử lý dữ liệu, có kiểu có thể khác (nhưng phải thích nghi hợp lệ); có thể trả primitive `int` rồi boxing.
- **`invokedType`:** chữ ký factory; với lambda không capture, có thể là `()Function`. **Không được nhầm** kiểu factory với kiểu generic của SAM.

Với input không tương thích tại runtime (ví dụ `String` được mong đợi nhưng caller gọi qua raw `Function` và truyền object khác), generated adapter/cast có thể ném `ClassCastException` tại invocation. Đây không phải lỗi “linkage chạy lại”; linkage đã chốt cấu trúc kiểu, còn giá trị runtime được kiểm tra khi gọi.

Các phép thích nghi trong `LambdaMetafactory` có quy tắc riêng: không phải chuyển đổi Java nào cũng được hỗ trợ, và generic type parameter không tồn tại nguyên vẹn ở bytecode. Nếu viết metafactory trực tiếp, cần kiểm tra **Javadoc của từng ràng buộc kiểu** thay vì suy diễn từ source syntax.

## 9. Khi nào capture có nghĩa là giữ bản sao, giữ tham chiếu hay giữ receiver?

| Biểu thức | Capture ở giai đoạn 2 | Điều xảy ra tại invocation |
| --- | --- | --- |
| `x -> x + 1` | Không có captured argument từ môi trường | Nhận `x` mới rồi cộng 1 |
| `x -> base + x` | Giữ **giá trị primitive** `base` | Nhận `x` rồi cộng với base đã giữ |
| `() -> box.get()` | Giữ **tham chiếu** `box` | Đọc **state hiện tại** của object |
| `box::get` | Giữ **receiver `box`** của bound method reference | Gọi method `get` trên object đã giữ |
| `this::process` | Giữ tham chiếu receiver `this` | Gọi `process` trên object ấy |
| `SomeClass::staticMethod` | Thường không cần receiver capture | Các đối số được cung cấp lúc invocation |
| `SomeClass::instanceMethod` (unbound) | Không capture receiver cụ thể | Receiver được truyền như đối số SAM đầu tiên |

Hai biểu thức `box::get` và `() -> box.get()` có thể cho hành vi rất giống nhau về đọc state, nhưng quy tắc evaluation và null-check của **bound method reference** không hoàn toàn trùng với lambda body. Không thay thế máy móc khi cần giữ đúng semantics với `null` hoặc side effect của biểu thức bên trái `::`.

**Quy tắc local variable:** khi lambda bắt một biến local `int base`, không có “con trỏ luôn cập nhật” đến slot local đó. Nếu muốn giá trị cập nhật, phải capture một object chứa state, và quản lý đồng bộ/thread-safety nếu nhiều thread có thể truy cập.

## 10. Sai lầm về hiệu năng, identity và vòng đời

**“Mỗi lần gọi lambda đều bootstrap.”** Sai. BSM liên kết **vị trí `invokedynamic`**, không chạy theo mỗi lời gọi `applyAsInt`. Nếu cùng lambda expression được đánh giá nhiều lần, target factory có thể được gọi nhiều lần để tạo hoặc lấy function object.

**“Capture chắc chắn tạo một instance mới.”** Sai. Javadoc của `LambdaMetafactory` không cam kết identity hoặc việc cấp phát mới. Với non-capturing lambda, tái sử dụng rất tự nhiên; nhưng cả ở trường hợp khác cũng không nên xây quy tắc nghiệp vụ từ `==` của function object.

**“Capture object nghĩa là chụp toàn bộ state object.”** Sai. Captured reference chỉ giữ tham chiếu; object có thể mutate. Nếu cần snapshot, lấy các giá trị cần thiết thành value object bất biến tại thời điểm tạo lambda.

**“`() -> sideEffect()` thực thi sideEffect lúc tạo lambda.”** Sai. Đây là lambda body; sideEffect chỉ chạy khi SAM invocation. Nhưng **biểu thức được đánh giá để làm captured receiver/argument** có thể có side effect ngay lúc tạo method reference hoặc chuẩn bị captured values. Cần phân biệt.

**“Một lambda có generic đầy đủ ở JVM.”** Sai. Bytecode dùng erased SAM signature và metadata của instantiated type để thiết lập các cast/adapter hợp lệ; không nên suy diễn từ `Function<String,Integer>` rằng runtime tạo class giữ đầy đủ generic parameters như một object type reified.

**“Tối ưu của JIT là nghĩa vụ của API.”** Sai. JVM có thể inline, dùng hidden class hoặc tối ưu function factory, nhưng không cam kết tên generated class, số object hoặc chuỗi machine instructions. Chỉ dựa vào contract của `CallSite` và functional interface.

**“Lambda luôn serializable.”** Sai. `LambdaMetafactory.altMetafactory` có hỗ trợ cờ như `FLAG_SERIALIZABLE`, `FLAG_MARKERS` và `FLAG_BRIDGES` khi cần thêm marker interface hoặc bridge methods, nhưng không phải mọi lambda đều có thể serialize và không nên mặc nhiên dựa vào cách triển khai. Việc deserialize lambda cần cơ chế hỗ trợ từ capturing class.

## 11. Phân loại lỗi theo giai đoạn

| Giai đoạn | Dấu hiệu | Kiểm tra |
| --- | --- | --- |
| **Linkage** | `LambdaConversionException` khi gọi metafactory trực tiếp | `Lookup` có quyền không? `factoryType` có trả interface không? `implMethod` có direct handle? `K + N = M` và các kiểu có phù hợp không? |
| **Linkage qua JVM** | `BootstrapMethodError` hoặc lỗi resolve tương ứng | BSM reference và static args có hợp lệ? `CallSite` có đúng descriptor của `invokedynamic`? |
| **Capture** | `WrongMethodTypeException` khi gọi `factory.invokeExact` với sai descriptor (trong code thủ công) | So `site.type()` với **tham số captured** và kiểu trả về factory |
| **Capture** | `NullPointerException` với bound instance receiver `null` | Kiểm tra receiver được đánh giá/đưa vào lúc capture |
| **Invocation** | `ClassCastException` khi adapter của generic SAM kiểm tra value sai kiểu | Xác định erased SAM type, instantiated type và kiểu của value thực tế |
| **Invocation** | `NullPointerException` hoặc exception do implementation method tự ném | Kiểm tra dữ liệu input, captured object state và stack trace của body |

Một `ClassCastException` hoặc `NullPointerException` **không tự chứng minh** đó là lỗi của `LambdaMetafactory`; implementation method có thể tự ném chúng. Kiểm tra stack trace và vị trí phát sinh.

Chẩn đoán chính xác theo thứ tự:

1. Tìm **chỉ thị `invokedynamic`** trong `javap -c -p` và bootstrap entry trong `javap -v -p`.
2. Ghi `factoryType`, `samMethodType`, `implMethod.type()` và `instantiatedMethodType`.
3. So số lượng captured arguments `K` với chênh lệch arity giữa implementation và SAM.
4. Phân biệt static args của bootstrap và dynamic captured values trên operand stack.
5. Hỏi lỗi xảy ra **khi link**, **khi tạo function object**, hay **khi gọi SAM**.
6. Với captured reference, kiểm tra state hiện tại, khả năng null và thread-safety.
7. Không dùng số lần gọi BSM hay tên lớp sinh để suy luận số object và số lần invocation.

## 12. Tự kiểm tra hiểu ba giai đoạn

**Câu 1.** Với `makeAdder(10)` và `makeAdder(20)`, có nhất thiết hai bootstrap linkage riêng không? Có cùng captured value không?  
**Đáp:** Cùng một **vị trí `invokedynamic`** trong `makeAdder` thường chỉ cần liên kết một lần sau khi thành công; các lần capture mang **hai giá trị khác nhau** `10` và `20`.

**Câu 2.** BSM có nhận giá trị `base=10` của lần gọi `makeAdder(10)` qua tham số `samMethodType` không?  
**Đáp:** Không. `samMethodType` là metadata tĩnh về signature SAM; giá trị `base` đến với **target factory** ở capture.

**Câu 3.** Implementation handle `(int,int)int`, SAM type `(int)int`, factory type `(int)IntUnaryOperator`. Có bao nhiêu captured parameters?  
**Đáp:** `M=2`, `N=1` nên `K=1`. Tham số `int` thứ nhất của implementation là captured value, tham số `int` thứ hai là invocation argument.

**Câu 4.** Sau khi tạo function object với `base=10`, gọi `applyAsInt(3)` ba lần có cần chạy lại capture không?  
**Đáp:** Không. Cùng function value tái sử dụng captured `10` và nhận invocation argument mới ở mỗi lần gọi (ở đây đều là `3`).

**Câu 5.** `box::get` đang giữ `AtomicInteger(5)`. Nếu sau đó `box.set(8)`, function có bắt buộc tiếp tục trả 5 không?  
**Đáp:** Không. Nó giữ **tham chiếu đến object**, nên lời gọi `getAsInt()` có thể nhìn thấy state hiện tại `8` (trong chương trình đã kiểm chứng, nó in 8).

**Câu 6.** Vì sao `javap` có thể cho thấy `invokedynamic` trong `compiledLambda` nhưng một lời gọi `compiled.applyAsInt(3)` lại thường là `invokeinterface`?  
**Đáp:** `invokedynamic` phục vụ factory/capture; `invokeinterface` gọi SAM trên function object đã nhận.

**Câu 7.** Có nên dùng `lambdaA == lambdaB` để xác định người dùng đang ở cùng phiên làm việc?  
**Đáp:** Không. Lambda object identity không phải hợp đồng được bảo đảm; dùng định danh nghiệp vụ được quản lý rõ ràng.

## Tài liệu chuẩn Java 17

- [`LambdaMetafactory`: Linkage, Capture, Invocation và `metafactory`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/LambdaMetafactory.html)
- [`MethodHandle` và `MethodType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html)
- [`CallSite`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/CallSite.html)
- [JVMS 17 — `invokedynamic` instruction](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html#jvms-6.5.invokedynamic)
- [JVMS 17 — resolution of dynamically-computed call sites](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.3.6)
- [JLS 17 — Lambda Expressions, `15.27`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.27)