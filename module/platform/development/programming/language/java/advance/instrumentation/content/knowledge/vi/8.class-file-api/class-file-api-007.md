# Chèn lệnh gọi helper thay vì viết lại toàn bộ thuật toán của ứng dụng

Trong Java instrumentation, ta thường chỉ cần thêm một điểm đo vào chương trình đã biên dịch: đếm lần gọi API, ghi một sự kiện, bắt đầu span hoặc thu số liệu trước một invocation. **Cách an toàn về phạm vi sửa đổi là chèn một lời gọi tới helper và giữ nguyên phần lớn bytecode gốc**, thay vì tự viết lại cả thuật toán nghiệp vụ.

Với Class-File API, ta có thể parse class file, đi vào method body bằng `ClassTransform`, phát sinh lệnh gọi helper tại `CodeTransform`, rồi chuyển tiếp instruction ban đầu thông qua `builder.with(element)`. Bài này đi từ operand stack tới một demo thực thi và các điều kiện để dùng trong Java agent.

**Phiên bản:** API chuẩn `java.lang.classfile` được hoàn thiện từ **JDK 24** (JEP 484), sau các phiên bản preview của JDK 22/23. Do đó tool biến đổi trong bài **cần JDK 24+**, không biên dịch được bằng Java 17/21. Lớp ứng dụng mẫu dùng cú pháp Java thông thường, nhưng các lệnh demo dùng JDK 24+ thống nhất để đảm bảo thư viện Class-File API tồn tại.

## 1. Vấn đề: cần hook mà không đổi bài toán

Xét lớp ứng dụng:

~~~java
public static int compute(int x) {
    int positive = Math.abs(x);
    return Math.max(positive, 10);
}
~~~

Ta muốn biết khi nào method gọi `Math.abs` hoặc `Math.max`. Ở mức ý tưởng, bytecode sau khi chèn tương đương:

~~~java
public static int compute(int x) {
    Probe.onCall("abs");
    int positive = Math.abs(x);
    Probe.onCall("max");
    return Math.max(positive, 10);
}
~~~

Đây là **diễn giải để học**: công cụ không chỉnh sửa file nguồn Java mà chỉnh các bytecode instructions trong file `.class`. Điểm quan trọng là lời gọi gốc vẫn tồn tại và vẫn được thực thi sau helper. Nếu đầu vào là `-7`, kết quả nghiệp vụ vẫn là `10`, miễn helper không phá đường chạy.

Một transformer tự xây lại toàn bộ method body có nguy cơ bỏ nhánh `if`, vòng lặp, `try/finally`, exception handler, monitor, các ô local, labels hoặc stack-map frames. Chèn một lời gọi nhỏ làm phạm vi thay đổi rõ hơn, dễ kiểm tra bằng `javap`, JVM verifier và test nghiệp vụ. **Nhỏ hơn không có nghĩa hoàn toàn vô hại**: helper có thể gây class loading, lỗi runtime, lock contention và overhead, nên vẫn phải đánh giá.

## 2. Các tầng mô hình của Class-File API

~~~text
Sample.class (byte[])
     |
     v
ClassFile.of().parse(...)  -> ClassModel
     |
     v
ClassTransform
     |-- các fields/attributes/methods khác: giữ nguyên
     |
     +-- method compute
             |
             v
          CodeTransform
             |-- gặp InvokeInstruction:
             |      thêm ldc tên lời gọi
             |      thêm invokestatic Probe.onCall
             |-- builder.with(element): giữ CodeElement gốc
     |
     v
ClassFile.transformClass(...) -> byte[] mới
~~~

| Thành phần | Nhiệm vụ |
| --- | --- |
| `ClassFile.of()` | Service đọc, xây và transform class files |
| `ClassFile.parse(byte[])` | Đọc bytes thành `ClassModel`, có phần được parse khi cần |
| `ClassModel` | Cấu trúc lớp: fields, methods, attributes |
| `MethodModel` | Tên, descriptor và Code của phương thức |
| `ClassTransform` | Biến đổi các class elements, chọn method cần sửa |
| `CodeTransform` | Xử lý lần lượt các code elements trong method |
| `CodeBuilder` | Phát sinh instruction mới và chuyển tiếp element cũ |
| `InvokeInstruction` | Mô hình của một lời gọi method trong bytecode |
| `ClassDesc` | Mô tả tên lớp helper, không cần nạp lớp vào tool |
| `MethodTypeDesc` | Mô tả chữ ký JVM của helper |
| `ClassFile.transformClass` | Dựng lại class bytes từ model và transform |

Ở điểm chèn, mẫu cốt lõi là:

~~~java
CodeTransform transform = (builder, element) -> {
    if (element instanceof InvokeInstruction call) {
        // Chèn instruction của helper trước call gốc.
    }
    builder.with(element); // Giữ element ban đầu.
};
~~~

Đoạn trên chỉ là **mảnh code minh họa**, không chạy độc lập; `builder.with(element)` có ý nghĩa then chốt. Nếu không chuyển tiếp element ban đầu, builder có thể **bỏ element đó khỏi file mới**. Khi element ấy chính là invocation cần quan sát, bạn đã vô tình xóa phép tính gốc.

## 3. Operand stack và vì sao lời gọi helper không lấy mất đối số

Bytecode JVM dùng operand stack. `Math.abs(int)` có descriptor `(I)I`, tức lấy một `int` và trả một `int`:

~~~text
Trước Math.abs:
    stack [ x:int ]
    invokestatic java/lang/Math.abs (I)I
    stack [ abs(x):int ]
~~~

Thiết kế helper:

~~~java
public static void onCall(String method)
~~~

Descriptor là `(Ljava/lang/String;)V`: lấy đúng một `String`, trả `void`. Bytecode chèn trước `Math.abs`:

~~~text
    stack [ x:int ]
    ldc "abs"
    stack [ x:int, "abs":String ]
    invokestatic Probe.onCall (Ljava/lang/String;)V
    stack [ x:int ]
    invokestatic java/lang/Math.abs (I)I
    stack [ abs(x):int ]
~~~

Helper chỉ tiêu thụ chuỗi mới đẩy lên phía trên; `x` vẫn nằm ở stack để invocation gốc sử dụng. Tương tự trước `Math.max(int,int)`, hai toán hạng đã có sẵn và vẫn giữ đúng vị trí khi helper trả `void`.

Nếu helper trả object hoặc `long` mà builder không xử lý, stack sẽ dư giá trị. Nếu chữ ký trong constant pool không khớp code helper thật, verifier hoặc linker có thể báo lỗi. Và dù stack hợp lệ, **helper ném exception sẽ khiến invocation gốc không chạy**. Cần kiểm tra đồng thời **bytecode correctness** và **business semantics**.

## 4. Các vị trí chèn thường dùng

| Vị trí | Quan sát được gì | Giới hạn |
| --- | --- | --- |
| Trước `InvokeInstruction` | Đường chạy đã tới call site | Chưa chứng minh lời gọi gốc thành công |
| Sau invocation | Invocation trả về bình thường | Không chạy nếu invocation ném lỗi |
| Method entry | Có lần bắt đầu method | Constructor có trạng thái `this` chưa khởi tạo |
| Trước return | Có lần return bình thường | Không tự bao phủ exceptional exit |
| Trước explicit `athrow` | Có lệnh ném tường minh | Không bao phủ mọi exception sinh trong lời gọi khác |
| Bọc toàn method như `finally` | Đo cả normal/exception exit | Cần sửa labels, handlers, frames và giữ nguyên ngoại lệ gốc |

Ví dụ thực hành chọn **trước invocation** vì chỉ cần sinh `ldc` rồi `invokestatic`, không cần tự sắp lại các giá trị trả về hoặc dựng lại exception table. Không suy luận rằng chỉ thêm hook tại `return` là thay thế đầy đủ `finally`.

## 5. Demo JDK 24+: ba file Java

Đặt ba file dưới đây trong **một thư mục thử nghiệm riêng**, dùng JDK 24 trở lên. Không dùng Maven/Gradle, ASM hay Byte Buddy. Đây là một **offline class-file transformer**: nó biến đổi file class trên đĩa để dễ kiểm tra. Phần sau giải thích nối vào Java agent.

### 5.1. Tệp `Sample.java`

~~~java
public final class Sample {
    public static int compute(int x) {
        int positive = Math.abs(x);
        return Math.max(positive, 10);
    }

    public static void main(String[] args) {
        System.out.println("RESULT=" + compute(-7));
    }
}
~~~

### 5.2. Tệp `Probe.java`

~~~java
public final class Probe {
    public static void onCall(String name) {
        System.out.println("HOOK_BEFORE=" + name);
    }
}
~~~

`System.out.println` giúp người học thấy kết quả. Helper production nên hạn chế I/O, cấp phát, khóa và exception; thường chỉ cập nhật counter hoặc queue hữu hạn rồi để reporter xử lý ngoài hot path.

### 5.3. Tệp `InjectHelper.java`

~~~java
import java.lang.classfile.ClassFile;
import java.lang.classfile.ClassTransform;
import java.lang.classfile.CodeTransform;
import java.lang.classfile.instruction.InvokeInstruction;
import java.lang.constant.ClassDesc;
import java.lang.constant.MethodTypeDesc;
import java.nio.file.Files;
import java.nio.file.Path;

public final class InjectHelper {
    private static final ClassDesc PROBE = ClassDesc.of("Probe");
    private static final MethodTypeDesc PROBE_TYPE =
            MethodTypeDesc.ofDescriptor("(Ljava/lang/String;)V");

    public static void main(String[] args) throws Exception {
        Path input = Path.of("Sample.class");
        byte[] original = Files.readAllBytes(input);
        ClassFile classFile = ClassFile.of();

        CodeTransform insertHelper = (builder, element) -> {
            if (element instanceof InvokeInstruction call) {
                builder.ldc(call.name().stringValue())
                       .invokestatic(PROBE, "onCall", PROBE_TYPE);
            }
            builder.with(element);
        };

        ClassTransform selectedMethods =
                ClassTransform.transformingMethodBodies(
                        method -> method.methodName().equalsString("compute"),
                        insertHelper);

        byte[] changed = classFile.transformClass(
                classFile.parse(original), selectedMethods);

        Files.write(input, changed);
        System.out.println("PATCHED=Sample.class");
    }
}
~~~

**Giải thích:**

1. `ClassDesc.of("Probe")` mô tả tên lớp helper trong bytecode. Nó không nạp `Probe` ở JVM của tool.
2. `MethodTypeDesc.ofDescriptor("(Ljava/lang/String;)V")` là chữ ký của `Probe.onCall(String)` trả `void`.
3. `ClassFile.of().parse(original)` nhận bytes nguồn và tạo `ClassModel`.
4. `ClassTransform.transformingMethodBodies` chỉ đi vào body của method tên `compute`; phần khác của lớp được chuyển tiếp.
5. `CodeTransform` phát sinh `ldc` tên method được gọi và `invokestatic Probe.onCall` **trước** `InvokeInstruction` hiện tại.
6. `builder.with(element)` giữ instruction cũ ngay sau hook. Do đó cả hai lời gọi `Math.abs` và `Math.max` vẫn tồn tại.
7. `transformClass` tạo bytecode mới; `Files.write` ghi lại `Sample.class` trong thư mục demo.

Method trong ví dụ chỉ có một overload `compute`; nếu có overload khác cần so cả method descriptor. Tương tự, nếu nội dung `compute` có thêm invocation thì tool sẽ instrument cả invocation mới: đây là hành vi **cố ý của demo**, nhưng trong ứng dụng thật phải lọc chặt hơn.

### 5.4. Biên dịch và chạy

~~~bash
javac --release 24 Sample.java Probe.java InjectHelper.java
~~~

`javac` phải thuộc JDK 24+ và hỗ trợ target `--release 24`. Compiler JDK 17/21 sẽ báo thiếu `java.lang.classfile`; đó là ràng buộc phiên bản, không phải lỗi import.

Chạy bản chưa biến đổi:

~~~bash
java Sample
~~~

Standard output:

~~~text
RESULT=10
~~~

Chạy tool để sửa `Sample.class`:

~~~bash
java InjectHelper
~~~

Standard output:

~~~text
PATCHED=Sample.class
~~~

Sau đó chạy lại ứng dụng:

~~~bash
java Sample
~~~

Standard output của các câu lệnh in trong demo:

~~~text
HOOK_BEFORE=abs
HOOK_BEFORE=max
RESULT=10
~~~

Hai hook chạy trước hai invocation gốc; phép tính vẫn trả `10` cho input đang thử. Đây là kết quả **được suy ra từ mã và hợp đồng API**, không phải bằng chứng test trên mọi máy. Khi dùng JDK/loader/classpath khác, hãy chạy thực tế để kiểm chứng.

**Lưu ý:** `InjectHelper` ghi đè file class **trong thư mục demo**. Nếu chạy tool lần nữa mà không biên dịch lại `Sample.java`, nó có thể chèn thêm hook trước cả những lời gọi `Probe.onCall` đã tạo lần đầu. Để test lại, hãy biên dịch lại lớp gốc trước mỗi lần patch, hoặc thay tool bằng cơ chế giữ input bất biến và viết output sang thư mục riêng.

### 5.5. Xem bytecode và kiểm tra hợp lệ

~~~bash
javap -c -p Sample
~~~

Trong method `compute`, có thể nhìn thấy thứ tự logic (bản rút gọn, **không phải output javap nguyên văn**):

~~~text
ldc           "abs"
invokestatic  Probe.onCall:(Ljava/lang/String;)V
invokestatic  java/lang/Math.abs:(I)I
...
ldc           "max"
invokestatic  Probe.onCall:(Ljava/lang/String;)V
invokestatic  java/lang/Math.max:(II)I
...
ireturn
~~~

Offset, chỉ số constant pool, load/store opcodes có thể khác, nhưng các lời gọi gốc phải còn sau hook. `Sample.java` vẫn nguyên văn, chỉ `Sample.class` được sửa.

Một kiểm tra runtime:

~~~bash
java -Xverify:all Sample
~~~

Nếu class hợp lệ, JVM nạp và thực thi được; output vẫn có ba dòng trên. `ClassFile` cũng cung cấp `verify(byte[])` để kiểm tra và thu danh sách lỗi trước khi ghi. Tuy nhiên verifier **không xác nhận** hook không làm đổi ngoại lệ, latency hay hành vi nghiệp vụ ở những nhánh chưa chạy.

## 6. Tại sao phải chuyển tiếp original element?

Khi transformer nhận một `CodeElement`, builder phải được đưa ra quyết định rõ ràng: **giữ, bỏ, sửa hoặc thêm**. Trong kỹ thuật chèn-only, mã thường là:

~~~java
CodeTransform correct = (builder, element) -> {
    if (element instanceof InvokeInstruction call) {
        builder.ldc(call.name().stringValue())
               .invokestatic(PROBE, "onCall", PROBE_TYPE);
    }
    builder.with(element);
};
~~~

So với phiên bản **cố ý sai**:

~~~java
CodeTransform broken = (builder, element) -> {
    if (element instanceof InvokeInstruction call) {
        builder.ldc(call.name().stringValue())
               .invokestatic(PROBE, "onCall", PROBE_TYPE);
        // Quên builder.with(element): lời gọi gốc mất.
    } else {
        builder.with(element);
    }
};
~~~

Ở phiên bản sai, một `Math.abs` gốc có thể bị loại, làm bytecode không còn trả đúng giá trị hoặc sai stack. Các element khác như load/store, label, branch, exception metadata cũng cần được giữ trừ khi đang thực hiện một phép biến đổi được thiết kế rõ. Class-File API có cơ chế transform/copy hiệu quả cho phần không đổi; không cần viết lại vòng lặp, `if` hay toàn bộ method body để chèn một lệnh gọi.

## 7. Chọn lọc call site theo owner/name/type

Lọc method bao ngoài theo tên `compute` mới là một tầng. Trong production, cần lọc thêm **lời gọi cụ thể**:

~~~java
// Trích đoạn trong CodeTransform đã có PROBE và PROBE_TYPE.
if (element instanceof InvokeInstruction call
        && call.owner().asInternalName().equals("java/lang/Math")
        && call.name().equalsString("abs")
        && call.typeSymbol().descriptorString().equals("(I)I")) {
    builder.ldc("abs")
           .invokestatic(PROBE, "onCall", PROBE_TYPE);
}
builder.with(element);
~~~

Đoạn này chỉ gắn hook trước `Math.abs(int)`. Nó không bắt `Math.abs(long)`, `Math.max` hoặc một class khác có method trùng tên. Các giá trị cần hiểu:

- `owner().asInternalName()` dùng dấu `/` trong JVM internal name.
- `name().equalsString(...)` so sánh tên method trong constant pool.
- `typeSymbol().descriptorString()` phân biệt overload, `(I)I` nghĩa là int → int.
- `opcode()` có thể kiểm tra `INVOKESTATIC`/`INVOKEVIRTUAL`/`INVOKEINTERFACE`/`INVOKESPECIAL` khi cần.
- `invokedynamic` là trường hợp riêng, không phải mọi invocation ở source đều thành `InvokeInstruction`.

Khi class có `compute(int)` và `compute(String)`, cần thêm method descriptor vào predicate của `ClassTransform.transformingMethodBodies` để không instrument cả hai. Đọc bytecode thực tế bằng `javap` trước khi xác định filter là cách kiểm chứng tốt.

## 8. Thiết kế helper contract phù hợp JVM

Một lời gọi bytecode cần:

~~~text
opcode      INVOKESTATIC
owner       Probe
name        onCall
descriptor  (Ljava/lang/String;)V
~~~

`ClassDesc` mô tả lớp owner, `MethodTypeDesc` mô tả tham số/return. Nếu bytecode nói helper là static nhưng runtime chỉ có instance method, có thể gặp `IncompatibleClassChangeError`; nếu method signature thiếu, có thể gặp `NoSuchMethodError`; nếu helper class không có trong runtime, có thể gặp `NoClassDefFoundError`. Các lỗi này không nhất thiết được phát hiện khi tool offline chỉ mới ghi file class.

Một helper production nên là API static nhỏ, không giữ tham chiếu `ClassLoader`/`Class<?>` dài hạn, không duyệt dữ liệu nghiệp vụ, không gửi network synchronously và có chính sách xử lý lỗi telemetry. Nếu helper cần đọc context, phải đóng scope ở đúng nhánh và tránh context leak trong thread pool.

Ví dụ helper dùng `println` chỉ dành cho học tập. Khi gọi trong ứng dụng thật, helper có thể chạy hàng triệu lần; chi phí CPU, allocation, contention, GC và I/O đều có thể làm sai hiệu năng dù kết quả tính toán giữ nguyên.

## 9. Tích hợp `ClassFileTransformer` trong Java agent

Demo offline nhận bytes bằng `Files.readAllBytes` và ghi output bằng `Files.write`. Trong agent, JVM trao `classfileBuffer` cho callback, và callback trả `byte[]` mới:

~~~text
OFFLINE: class bytes -> ClassFile.parse -> transformClass -> Files.write
AGENT:   classfileBuffer -> ClassFile.parse -> transformClass -> return bytes
~~~

Mảnh code ý tưởng nằm **bên trong một phương thức transform(...)**, nơi `classFile`, `selectedTransform` và `failures` đã được khởi tạo sẵn:

~~~java
if (!"demo/app/Sample".equals(className)) {
    return null;
}
try {
    return classFile.transformClass(
            classFile.parse(classfileBuffer), selectedTransform);
} catch (RuntimeException ex) {
    failures.incrementAndGet();
    return null;
}
~~~

`return null` theo contract `ClassFileTransformer` có nghĩa **không sửa bytecode ở lượt này**. Nó khác `builder.with(element)` của `CodeTransform`, nghĩa là chuyển tiếp một element khi đang xây bytecode mới.

Chính sách catch và trả null trong snippet là **best-effort**: nếu instrument là bắt buộc cho tính đúng đắn/bảo mật, phải có fail policy rõ, không âm thầm bỏ lỗi. Agent đang chạy phải là JVM có Class-File API chuẩn (JDK 24+ với code mẫu). Nếu muốn agent hỗ trợ JVM JDK 17, phải dùng công cụ biến đổi khác phù hợp hoặc một kiến trúc build/offline khác.

Các điểm an toàn cho callback:

1. Lọc `className` sớm, nhớ nó có thể null.
2. Khởi tạo helper, parser và dữ liệu filter trước khi đăng ký transformer.
3. Không dùng `Class.forName` để buộc nạp chính lớp đang được JVM định nghĩa.
4. Không log, lấy lock nặng hay export đồng bộ trong callback class loading.
5. Loại trừ package/helper của agent để tránh self-instrumentation.
6. Kiểm tra hỗ trợ và giới hạn retransform/redefine nếu áp dụng sau khi class đã load.

## 10. Idempotence và chuỗi transforms

Nếu transform chạy lại trên bytes đã patch, hook sẽ bị **nhân đôi** nếu không có guard. Kỹ thuật phòng:

- Luôn transform từ artifact gốc bất biến và ghi output riêng có checksum.
- Exclude invocation tới chính helper, nhưng biết rằng cách này **chưa ngăn** thêm hook lần hai trước invocation gốc.
- Có marker idempotence hoặc nhận diện instruction pattern chính xác theo owner/name/descriptor.
- Tránh đăng ký cùng transformer nhiều lần; kiểm tra khi agent có nhiều tầng composition.
- Nếu dùng `andThen`, nhớ transform sau có thể nhận chính instruction do transform trước sinh ra.

Với JVM retransformation, bytecode đầu vào và thứ tự transformer phụ thuộc cơ chế JVM/registration. Không khẳng định mọi lượt retransform đều bắt đầu từ đúng file `.class` nguyên bản hoặc đều đã có hook; phải kiểm tra trên JVM thực tế và viết test chống duplicate.

## 11. Class loader và module là điều kiện chạy thật

Trong demo, `Probe.class` và `Sample.class` cùng classpath nên liên kết dễ dàng. Ở hệ thống thật:

- Target có thể ở custom/plugin/webapp class loader, helper nằm ở loader khác không nhìn thấy.
- Lớp được nạp bởi bootstrap loader không tự thấy helper chỉ có trong JAR agent ở system loader.
- Named module có ràng buộc readability/exports, không tự được mở quyền chỉ nhờ `ClassDesc.of(...)`.
- Hot redeploy có thể tạo nhiều class loaders; cache strong reference của helper/agent có thể gây leak.
- Instrument lại helper hoặc logging/exporter có thể tạo recursion, lock cycle hoặc bùng nổ metrics.

Cần chọn vị trí phân phối helper phù hợp với loader/module của target, dùng bootstrap append/module adjustment **chỉ khi cần và có kiểm tra quyền**, và thử trực tiếp với runtime class-loader topology. Chỉ cần tool offline biên dịch được chưa đủ chứng minh helper invocation chạy được ở mọi ứng dụng.

## 12. JVM verifier, stack map và exception behavior

Để method sau chèn có thể nạp, cần giữ:

| Bất biến | Rủi ro nếu sai |
| --- | --- |
| Operand stack height/type | `VerifyError` hoặc runtime mismatch |
| `max_stack`, `max_locals` | Frame không phù hợp với instruction mới |
| `StackMapTable` | Verification lỗi ở branch/handler |
| Labels và branch targets | Điều hướng nhánh sai |
| Exception handlers | Lỗi có thể bị bắt khác trước |
| Method reference/opcode | `NoSuchMethodError` hoặc `IncompatibleClassChangeError` |
| Constructor initialization | Không được dùng `this` chưa khởi tạo |
| Class file version | JVM cũ có thể không load được |
| Attributes/metadata | Framework/debugger có thể phụ thuộc |

Class-File API giúp xây lại file class và quản lý cấu trúc, nhưng **vẫn cần verify**. Hãy kết hợp `ClassFile.verify`, `java -Xverify:all`, `javap` và behavioral tests. Nếu helper ném exception bên trong vùng try của method gốc, exception đó có thể đi vào handler của method gốc và làm đổi kết quả. Verifier không phát hiện loại sai lệch ngữ nghĩa này.

Đừng chèn hook dùng `this` ở đầu constructor trước khi `super(...)` đã hoàn tất mà không hiểu quy tắc uninitialized instance. Đừng coi việc thêm hook trước `return` là bao phủ mọi đường `throw`.

## 13. Chi phí và quản lý dữ liệu chẩn đoán

Một lời gọi helper tuy ít instruction nhưng xuất hiện trên hot path. Để đo overhead hợp lý:

1. Baseline không patch.
2. Bản patch gọi helper **no-op**.
3. Bản patch ghi counter hoặc bounded queue.
4. Bản patch có exporter/collector thật.

So sánh p50/p95/p99 latency, throughput, CPU, allocation/GC, số event bị drop và chi phí backend. Cần giới hạn payload, sampling, number of labels và retention. Tránh metric labels cardinality cao như user ID hoặc raw URL nhiều giá trị. Nếu collector mất kết nối, helper không nên chặn request vô hạn chỉ để giữ telemetry.

Nếu dữ liệu audit nghiệp vụ cần bền vững tuyệt đối, hãy dùng kênh audit/transaction riêng; log/trace trong instrumentation best-effort có thể mất tín hiệu.

## 14. QA theo từng mức

| Bài thử | Kết luận được phép rút ra |
| --- | --- |
| Bản gốc in `RESULT=10` | Baseline của input `-7` |
| Bản patch in hai `HOOK_BEFORE` và `RESULT=10` | Vị trí chèn đúng cho testcase |
| `javap -c -p Sample` thấy hai lời gọi `Math` còn nguyên | Original invocations chưa bị xóa |
| `java -Xverify:all Sample` qua | Bytecode hợp lệ ở JVM thử |
| Helper thiếu hoặc sai descriptor | Biết failure mode linkage/verify |
| Helper cố tình throw | Hiểu contract exception bị ảnh hưởng |
| Patch lại lần hai | Xác định duplicate/idempotence problem |
| Method overload | Filter cần thêm descriptor |
| Target ở custom loader/module | Helper visibility cần kiểm tra |
| Tải cao và nhiều luồng | Đo overhead, contention, drop |
| Agent live/retransform | Kiểm tra callback, recursion và JVM limitations |

Bổ sung tests với input biên, nhánh exception, concurrency và transaction behavior. Chỉ chạy một input mẫu không chứng minh tương đương cho mọi thuật toán.

## 15. Các sai lầm thường gặp

- **Quên `builder.with(element)`:** xóa instruction gốc, làm đổi thuật toán và stack.
- **Sai chữ ký helper:** mismatch descriptor/opcode, gây verify hoặc linkage error.
- **Lọc chỉ theo tên method:** instrument nhầm overload hoặc những class trùng tên.
- **Không exclude helper calls:** tự tạo thêm hook và recursion.
- **Chạy patch nhiều lần:** duplicate instrumentation và overhead tăng.
- **Nhầm event before-call với call thành công:** hook chạy trước dù invocation sau đó ném lỗi.
- **Cho rằng Class-File API có từ JDK 17:** code phải dùng JDK 24+.
- **Chỉ test JVM verifier:** bytecode hợp lệ vẫn có thể làm chậm hoặc sai nghiệp vụ vì helper.
- **Bỏ qua class loader/module:** class compile được nhưng helper không resolve ở runtime.
- **Ghi log/network trực tiếp ở hot path:** tăng contention và latency.
- **Chèn ở entry của constructor không xét `this`:** có nguy cơ vi phạm quy tắc initialization.
- **Coi return-hook là finally:** không bao phủ exceptional exits.

## 16. Câu hỏi tự kiểm tra

1. Vì sao `builder.with(element)` giữ được lời gọi `Math.abs` gốc?
2. Helper có chữ ký `(Ljava/lang/String;)V` sử dụng operand stack thế nào để không làm mất `int x`?
3. `ClassTransform.transformingMethodBodies` có lợi gì khi chỉ muốn sửa một method?
4. Lọc `Math.abs(int)` cần owner, name, descriptor và opcode gì?
5. Tại sao `InvokeInstruction` không bao phủ mọi dạng gọi lambda?
6. Nếu helper ném RuntimeException, method gốc có chắc chắn chạy tới invocation sau nó không?
7. Vì sao phép biến đổi có thể verify thành công nhưng vẫn làm tăng p99 latency?
8. Nếu có nhiều class loaders, cần kiểm tra gì để bảo đảm chúng truy cập được helper?
9. Chạy tool hai lần mà không reset có thể làm gì với chính `Probe.onCall`?
10. Khi chuyển từ offline sang agent, `return null` của `ClassFileTransformer` khác `builder.with(element)` như thế nào?
11. Vì sao phải làm thêm unit tests cho exception handler và constructor?
12. Nếu muốn nạp agent trên JDK 17, bạn có thể dùng nguyên ví dụ dùng `java.lang.classfile` không?

## 17. Quy trình áp dụng

1. Chốt mục đích và vị trí quan sát, xác định semantics "before", "after" hoặc "finally".
2. Chọn class/method/call site theo descriptor cụ thể, giới hạn phạm vi nhỏ.
3. Thiết kế helper static với signature, visibility và failure policy ổn định.
4. Chèn instruction mới và chuyển tiếp `CodeElement` gốc qua `builder.with`.
5. Sinh class file từ bytes gốc bất biến; kiểm tra idempotence.
6. Xem `javap` và verify bytecode, giữ class metadata cần thiết.
7. Chạy behavioral tests với các nhánh và lỗi khác nhau, kiểm tra module/class loader.
8. Đo latency, throughput, allocation, GC và sức khỏe telemetry.
9. Nếu tích hợp agent, hạn chế công việc trong callback, loại trừ helper, theo dõi transform failures.
10. Canary và chuẩn bị rollback khi phát hiện lỗi linkage, correctness hoặc overhead.

## 18. Tài liệu chính thức

- [JEP 484 – Class-File API](https://openjdk.org/jeps/484): Class-File API được chuẩn hóa trong JDK 24.
- [Oracle JDK 24 – package java.lang.classfile](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/package-summary.html): cơ chế parse/build/transform và hướng dẫn thêm instrumentation.
- [Oracle JDK 24 – ClassTransform](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassTransform.html): `transformingMethodBodies` và các factory transforms.
- [Oracle JDK 24 – CodeBuilder](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/CodeBuilder.html): `ldc`, `invokestatic`, `with`.
- [Oracle JDK 24 – ClassFile](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassFile.html): `parse`, `transformClass`, `verify`.
- [Oracle JDK 24 – ClassFileTransformer](https://docs.oracle.com/en/java/javase/24/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): điểm nối Java agent và cách trả `null` khi không biến đổi.

**Điểm cần nhớ:** `CodeTransform` chỉ cần phát sinh thêm một lời gọi helper tại đúng vị trí và giữ các phần tử gốc bằng `builder.with(element)`. Đừng viết lại toàn bộ thuật toán ứng dụng khi chỉ cần quan sát một call site; đồng thời luôn xác minh helper có thể chạy an toàn trong ngữ cảnh class loader, exception và workload thực.
