# Giữ tương thích khi nhiều Java agent cùng chỉnh một phương thức

Khi một ứng dụng chạy cùng hai Java agent, ví dụ agent A ghi trace và agent B đo thời gian, **cả hai có thể biến đổi bytecode của cùng một lớp và cùng một phương thức**. Các phép sửa không hoạt động như hai bản vá độc lập lên file .class ban đầu: JVM gọi **ClassFileTransformer** theo thứ tự quy định, và byte[] mà transformer trước trả về trở thành đầu vào của transformer tiếp theo. Nếu B xây lại method từ bytes trên đĩa, xóa instruction A đã thêm hoặc giả định cấu trúc method luôn ở trạng thái ban đầu, tính năng của A có thể biến mất, bị chèn trùng, hoặc JVM có thể từ chối class file cuối cùng.

Bài học giải thích cách JVM ghép nhiều transformer; cách viết phép biến đổi bảo toàn các sửa đổi hợp lệ trước đó; rủi ro với **retransform/redefine**, class loader, module và concurrency; và một ví dụ Java 17+ chạy được trong đó **hai lượt -javaagent cùng sửa kết quả của một method** để thấy rõ ảnh hưởng của thứ tự.

## 1. Mục tiêu và mô hình tổng quát

Hoàn thành bài này, bạn cần:

1. Giải thích vì sao transformer B có thể nhận bytes **đã được A sửa**, không phải bytes gốc B0.
2. Biết **bốn nhóm transformer** theo thứ tự JVM áp dụng và phân biệt thứ tự nhóm với thứ tự đăng ký.
3. Biết khi nào **return null**, khi nào trả **mảng byte mới**, và vì sao không sửa trực tiếp **classfileBuffer**.
4. Giữ nguyên semantics method: return, exception, stack/frame, synchronization, annotations và metadata.
5. Thiết kế phép biến đổi có tính **idempotent** để không chèn advice trùng sau khi transform/retransform.
6. Thử nghiệm A, B, A+B, B+A, đăng ký lặp, lớp load muộn và retransform.
7. Nhận diện trường hợp hai agent **không thể tương thích về nghiệp vụ** nếu không có cơ chế điều phối.

~~~text
Class bytes B0 (trước transformer)
        │
        ▼
Transformer A ── return B1 = thêm advice đếm invocation
        │
        ▼
Transformer B nhận B1, không phải bản gốc B0
        │
        └── return B2 = giữ A + thêm advice đo duration
        ▼
Các transformer tiếp theo (nếu có)
        │
        ▼
JVM verify/link/define class từ bytes cuối cùng
        │
        ▼
Ứng dụng thực thi method theo định nghĩa đã được chấp nhận
~~~

**Nguyên tắc cốt lõi:** transformer nào không muốn sửa lớp thì **return null** ở lượt của mình; transformer nào muốn sửa thì xử lý **bytes hiện tại trong chuỗi** và trả mảng mới có class file hợp lệ. Kết quả callback chưa tự chứng minh JVM đã chấp nhận hoặc ứng dụng đã biểu hiện hiệu ứng cần có.

## 2. Hợp đồng ghép nhiều ClassFileTransformer

### 2.1. Mỗi kết quả trở thành input của bước sau

Với hai transformer A và B:

| A trả về | B trả về | Kết quả của đoạn A → B |
| --- | --- | --- |
| **null** | **null** | Giữ nguyên B0 |
| B1 | **null** | Tiếp tục bằng B1 |
| **null** | B2 | B2 được xây từ B0 |
| B1 | B2 | B2 phải được xây từ B1 |
| B1 | B2 không hợp lệ | JVM có thể từ chối định nghĩa cuối |

Nếu A **return null**, điều đó không có nghĩa “không agent nào được biến đổi lớp”. Nếu A trả B1, B không thể hợp lệ tuyên bố rằng mọi instruction trong B1 đều do ứng dụng gốc tạo ra. Trong một method đang được nhiều agent quan sát, điều quan trọng là B **phân tích cả code đã có**, giữ các thuộc tính hợp lệ và chỉ sửa phần B sở hữu.

### 2.2. Thứ tự bốn nhóm transformer trong Java 17

Theo Javadoc của **ClassFileTransformer**, JVM xử lý theo nhóm:

1. **Java transformer không hỗ trợ retransformation**: đăng ký bằng **addTransformer(t)** hoặc **addTransformer(t, false)**.
2. **Native transformer không hỗ trợ retransformation**.
3. **Java transformer hỗ trợ retransformation**: đăng ký bằng **addTransformer(t, true)**.
4. **Native transformer hỗ trợ retransformation**.

**Trong từng nhóm**, transformer được gọi theo thứ tự đăng ký. Native transformer liên quan sự kiện **ClassFileLoadHook** của JVM Tool Interface. Với startup agent qua **-javaagent**, JVM gọi các **premain** theo thứ tự khai báo trên dòng lệnh, nhưng **không thể suy luận transformer của JAR đầu luôn chạy trước transformer của JAR sau** nếu chúng được đăng ký ở các nhóm khác nhau.

Ví dụ:

~~~text
-javaagent:agent-a.jar -javaagent:agent-b.jar

premain A: addTransformer(A, true)   → nhóm Java có retransform
premain B: addTransformer(B, false)  → nhóm Java không retransform

Khi định nghĩa class mới:
    B được gọi trước A do thứ tự NHÓM.
~~~

Nếu A và B cùng gọi **addTransformer(t, false)**, chúng thuộc cùng nhóm và chạy theo thứ tự đăng ký. Nếu agent B được attach sau startup hoặc một framework remove rồi add lại transformer, thứ tự thực tế có thể khác thời điểm bạn thiết kế pipeline.

### 2.3. Không giả định mọi phép biến đổi giao hoán

Gọi A(x) là bytes sau biến đổi của A, B(x) là bytes sau biến đổi của B:

- **B(A(B0))** là kết quả khi A trước B.
- **A(B(B0))** là kết quả khi B trước A.

Hai biểu thức có thể khác nhau ngay cả khi mỗi transformer đều hợp lệ khi chạy riêng. Với log, tracing, timeout hoặc security advice, sự khác biệt có thể đổi cái gì được đo, thứ tự xử lý exception hay các sự kiện được ghi. Cần nêu rõ trong tài liệu triển khai: **thứ tự nào được hỗ trợ, kết quả mong đợi là gì và có thể đảo thứ tự hay không**.

## 3. Quy tắc viết transformer để không phá agent khác

### 3.1. Luôn dùng classfileBuffer hiện tại

~~~java
// Đoạn minh họa trong ClassFileTransformer.transform(...).
if (!"com/example/Service".equals(className)) {
    return null;
}
byte[] next = applyOnlyMyChanges(classfileBuffer);
return next; // null nếu không cần sửa, byte[] mới nếu đã sửa.
~~~

Đây là pseudocode vì **applyOnlyMyChanges** phụ thuộc thư viện biến đổi. Nhưng ý nghĩa rõ ràng: input là **classfileBuffer được JVM truyền vào callback hiện tại**.

Thiết kế sai:

~~~java
// Phản ví dụ ý tưởng, không phải Java runnable.
byte[] pristine = readClassBytesFromOriginalJar("com/example/Service");
byte[] replacement = instrument(pristine);
return replacement; // Xóa những instruction mà agent trước đã chèn.
~~~

Một agent có thể đọc bytes trên đĩa để phân tích hoặc so sánh, nhưng không được âm thầm **thay thế toàn bộ chuỗi biến đổi** bằng bản nó vừa xây từ file gốc. Điều đó dễ xóa metric/log/tracing của agent trước.

### 3.2. Return null khi không đổi; không mutate input

~~~java
// Mẫu đúng về quyền sở hữu buffer:
if (!shouldTransform(className, loader)) {
    return null;
}
byte[] copy = classfileBuffer.clone();
modifyCopyAsValidClassFile(copy);
return copy;
~~~

Đây cũng là pseudocode. **classfileBuffer không được sửa trực tiếp**, kể cả khi cuối cùng return null. Nếu xử lý thực tế xác định không cần biến đổi, trả **null** và tránh clone/tính lại bytecode. Không dùng **new byte[0]** để biểu thị “không thay đổi”.

Transformer trả một **byte[] mới** chỉ chứng minh nó cung cấp dữ liệu thay thế. JVM và các transformer sau vẫn phải kiểm tra và xử lý; mảng khác tham chiếu nhưng nội dung giống cũ không phải bằng chứng có hiệu ứng mới.

### 3.3. Bảo toàn mọi instruction và metadata không thuộc quyền mình

Khi chỉnh một method, phải cân nhắc:

- Tên và **descriptor** chính xác của method; không chỉ lọc theo tên vì có overload.
- Các instruction đang có, bao gồm callsite của agent khác.
- **Max stack, local variables, StackMapTable**, branch targets, try/catch/finally handlers.
- **Annotations, generic signature, line numbers, local-variable tables** nếu consumer khác cần chúng.
- **Access flags**, method semantics, constructors, synchronized và các đặc tính ABI.
- Class loader và module của lớp được biến đổi; cùng FQCN ở hai defining loader khác nhau là hai runtime class khác nhau.

Với ASM, cần hiểu đường **ClassReader → ClassVisitor/MethodVisitor → ClassWriter** và gọi các bước forward trong visitor khi không chủ động thay thế chúng. Với Byte Buddy, cần nắm cách match method, thứ tự transformer và đặc điểm advice/delegation, tránh cấu hình “replace method body” khiến code do agent trước đưa vào biến mất.

Đừng tự tin rằng việc bật **COMPUTE_MAXS** sẽ tự sửa mọi vấn đề stack-map frame; frame computation và common superclass resolution có điều kiện riêng. Cần kiểm tra trên JVM/JDK thực và với class loader phù hợp.

### 3.4. Tính idempotent có chủ đích

Nếu cùng agent được nạp hai lần, hoặc cùng class được retransform nhiều lần, advice có thể bị chèn trùng. Cách hạn chế:

- Trước khi chèn, kiểm tra xem method đã có **dấu hiệu nhận dạng riêng của agent mình** chưa (ví dụ callsite đến helper trong namespace của mình).
- Không dùng marker trống nghĩa như **INSTRUMENTED** chung cho mọi agent; tránh va chạm tên và sai ownership.
- Nếu code đã mang đúng advice của agent, **return null** cho callback hiện tại.
- Khi cache trạng thái, dùng class identity đủ chặt (class name + defining loader/module khi cần); đừng chỉ dựa vào tên string.
- Không mặc định thêm field/method trong **retransform/redefine**, vì JVM thường không cho thay đổi class schema kiểu đó.

Idempotent của từng phép biến đổi **không đồng nghĩa** A và B có thể đổi chỗ tùy ý; một phép không chèn trùng vẫn có thể phụ thuộc output của agent khác.

## 4. Ví dụ Java 17+ chạy được: hai lượt agent sửa cùng Target.value()

Ví dụ dùng **một agent JAR được khai báo hai lần** trên dòng lệnh với options A và B. Theo đặc tả Java Instrumentation, nhiều tham số **-javaagent** được phép trỏ tới cùng jarpath; JVM gọi premain theo thứ tự khai báo. Mỗi lần premain tạo **một instance transformer riêng**, nên ta có hai transformer và thấy được chaining mà không phải xử lý xung đột dependency giữa hai JAR thực.

Chủ đề của ví dụ là cách chúng cùng sửa phương thức **Target.value()**. A đổi literal string **ORIG000 → STEP100**, B đổi **STEP100 → STEP200**. Cả ba đều có **7 byte ASCII**, cho phép sửa đúng một entry constant pool trong class demo mà không đổi độ dài class file. Đây là bài tập quan sát chain, **không phải cơ chế weaving method tổng quát**.

### 4.1. File DemoApp.java

~~~java
// File: DemoApp.java
public final class DemoApp {
    public static void main(String[] args) throws Exception {
        // Tải Target chủ động sau khi các premain đã chạy.
        Class<?> target = Class.forName("Target");
        java.lang.reflect.Method method =
                target.getDeclaredMethod("value");
        System.out.println("VALUE=" + method.invoke(null));
    }
}

class Target {
    static String value() {
        return "ORIG000";
    }
}
~~~

**DemoApp** và **Target** thuộc cùng default package và class loader của ứng dụng trong ví dụ. **Class.forName("Target")** giúp tạo điểm dùng lớp rõ ràng sau khi JVM cài agent. Method package-private có thể được gọi từ DemoApp cùng package/module. Dự án thật nên dùng package đặt tên rõ ràng và quản lý quyền truy cập phù hợp.

### 4.2. File ChainAgent.java

~~~java
// File: ChainAgent.java
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.nio.charset.StandardCharsets;
import java.security.ProtectionDomain;

public final class ChainAgent implements ClassFileTransformer {
    private final String mode;

    private ChainAgent(String mode) {
        this.mode = mode;
    }

    public static void premain(String options, Instrumentation inst) {
        if (!"A".equals(options) && !"B".equals(options)) {
            throw new IllegalArgumentException("Use mode A or B");
        }

        inst.addTransformer(new ChainAgent(options), false);
        System.out.println("REGISTER " + options);
    }

    @Override
    public byte[] transform(
            ClassLoader loader,
            String className,
            Class<?> classBeingRedefined,
            ProtectionDomain protectionDomain,
            byte[] classfileBuffer) {

        if (!"Target".equals(className)) {
            return null;
        }

        String from = "A".equals(mode) ? "ORIG000" : "STEP100";
        String to = "A".equals(mode) ? "STEP100" : "STEP200";

        byte[] result = swapUtf8(classfileBuffer, from, to);
        System.out.println("TRANSFORM " + mode + " "
                + (result == null ? "SKIP" : "CHANGED"));
        return result;
    }

    private static byte[] swapUtf8(byte[] original,
                                   String from, String to) {
        byte[] oldValue = from.getBytes(StandardCharsets.US_ASCII);
        byte[] newValue = to.getBytes(StandardCharsets.US_ASCII);
        if (oldValue.length != newValue.length || original.length < 10
                || (original[0] & 0xff) != 0xca
                || (original[1] & 0xff) != 0xfe
                || (original[2] & 0xff) != 0xba
                || (original[3] & 0xff) != 0xbe) {
            return null;
        }

        int count = u2(original, 8);
        int p = 10;

        for (int i = 1; i < count; i++) {
            int tag = original[p++] & 0xff;
            switch (tag) {
                case 1 -> { // CONSTANT_Utf8
                    int size = u2(original, p);
                    p += 2;
                    if (size == oldValue.length
                            && matches(original, p, oldValue)) {
                        byte[] copy = original.clone();
                        System.arraycopy(newValue, 0, copy,
                                         p, newValue.length);
                        return copy;
                    }
                    p += size;
                }
                case 3, 4, 9, 10, 11, 12, 17, 18 -> p += 4;
                case 5, 6 -> {
                    p += 8;
                    i++; // long/double chiếm hai slot.
                }
                case 7, 8, 16, 19, 20 -> p += 2;
                case 15 -> p += 3;
                default -> throw new IllegalArgumentException(
                        "Unknown constant-pool tag: " + tag);
            }
        }
        return null;
    }

    private static int u2(byte[] bytes, int index) {
        return ((bytes[index] & 0xff) << 8)
                | (bytes[index + 1] & 0xff);
    }

    private static boolean matches(byte[] bytes, int p,
                                   byte[] sought) {
        if (p + sought.length > bytes.length) {
            return false;
        }
        for (int i = 0; i < sought.length; i++) {
            if (bytes[p + i] != sought[i]) {
                return false;
            }
        }
        return true;
    }
}
~~~

Ý nghĩa:

1. **premain** tạo **new ChainAgent(options)**; hai lần -javaagent nghĩa là hai transformer instance độc lập được đăng ký ở cùng nhóm **canRetransform=false**.
2. Chỉ lớp nội bộ tên **Target** được xét; các lớp khác **return null**, không bị parse hoặc copy.
3. A chỉ đổi **ORIG000** thành **STEP100**, rồi B có thể đọc bytes đã đổi đó và đổi tiếp **STEP100** thành **STEP200**.
4. B chạy trước A thì không tìm thấy **STEP100**, nên **return null**. A sau đó vẫn tìm thấy **ORIG000** và sửa một lần.
5. **original.clone()** tạo mảng khác để thay đúng entry UTF8 có cùng độ dài; **classfileBuffer không bị mutate**.
6. **TRANSFORM ... CHANGED** là log về mảng đã cung cấp; kết quả **VALUE=...** trong DemoApp xác nhận class thực sự dùng literal mới.

**Giới hạn kỹ thuật:** Helper parser constant pool trên chỉ dành cho **class file hợp lệ do javac tạo trong ví dụ**, thiếu kiểm tra bounds đầy đủ cho input giả/hỏng, không xử lý Modified UTF-8 tùy ý, không hỗ trợ nhiều phép sửa phức tạp và không quản lý branch/StackMapTable. Không dùng nó để sửa class bất kỳ. Với sản phẩm thật nên dùng thư viện bytecode, giữ nguyên metadata không liên quan, kiểm tra input và giới hạn retransform/redefine.

### 4.3. File agent.mf

Tạo file văn bản **agent.mf** với newline cuối file:

~~~text
Manifest-Version: 1.0
Premain-Class: ChainAgent
~~~

Ví dụ chỉ xử lý class load mới nên không cần **Can-Retransform-Classes**. Manifest chứa tên nhị phân của lớp agent, không phải đường dẫn file .class.

### 4.4. Biên dịch, đóng gói và chạy

Đặt ba file **DemoApp.java**, **ChainAgent.java**, **agent.mf** vào cùng thư mục. Dùng JDK 17+:

~~~bash
javac --release 17 DemoApp.java ChainAgent.java
jar cfm chain-agent.jar agent.mf ChainAgent.class
java -javaagent:chain-agent.jar=A -javaagent:chain-agent.jar=B -cp . DemoApp
~~~

Output mong đợi trên HotSpot Java 17:

~~~text
REGISTER A
REGISTER B
TRANSFORM A CHANGED
TRANSFORM B CHANGED
VALUE=STEP200
~~~

A trả bytes chứa **STEP100**; B nhận bytes đó và sửa thành **STEP200**; JVM định nghĩa **Target** với literal cuối. Đảo thứ tự:

~~~bash
java -javaagent:chain-agent.jar=B -javaagent:chain-agent.jar=A -cp . DemoApp
~~~

Output:

~~~text
REGISTER B
REGISTER A
TRANSFORM B SKIP
TRANSFORM A CHANGED
VALUE=STEP100
~~~

B đã bỏ qua vì chưa có STEP100. A chạy sau tạo STEP100 nhưng không có lượt B nào nữa để đổi thành STEP200. Chạy không agent:

~~~bash
java -cp . DemoApp
~~~

~~~text
VALUE=ORIG000
~~~

Chạy A đơn lẻ:

~~~bash
java -javaagent:chain-agent.jar=A -cp . DemoApp
~~~

~~~text
REGISTER A
TRANSFORM A CHANGED
VALUE=STEP100
~~~

Chạy A hai lần để kiểm tra không nhân đôi kết quả:

~~~bash
java -javaagent:chain-agent.jar=A -javaagent:chain-agent.jar=A -cp . DemoApp
~~~

~~~text
REGISTER A
REGISTER A
TRANSFORM A CHANGED
TRANSFORM A SKIP
VALUE=STEP100
~~~

Lượt A thứ hai không thấy ORIG000 nên trả null. Điều đó minh họa idempotency **của quy tắc thay chuỗi này**; một agent chèn instruction chưa chắc tự động idempotent.

Dùng **javap -c -p Target** có thể thấy class trên đĩa vẫn trả **ORIG000**: ví dụ transform định nghĩa lớp **trong JVM**, không sửa file .class trên ổ đĩa.

### 4.5. Khi hai agent là hai JAR thực

Trong hệ thống thật, A và B thường có **hai Premain-Class, hai JAR và dependency khác nhau**. Nếu cùng nhóm, cơ chế chaining ở trên vẫn áp dụng. Khác biệt nằm ở việc mỗi agent có thể đăng ký nhiều transformer, thuộc nhóm capability khác nhau, nạp helper từ loader/module khác nhau, hoặc dùng các phiên bản bytecode library xung đột. Vì vậy cần quan sát thứ tự **registration thực tế** và thử compatibility trên đúng tổ hợp phiên bản.

## 5. Đảm bảo hai advice cùng một method không phá semantics

Ví dụ đổi constant pool dễ hiểu vì không thêm control flow. Với method thật, A muốn đếm request và B muốn ghi duration, cả hai có thể chèn entry/exit advice:

~~~java
// Ví dụ source-level để minh họa ngữ nghĩa; không phải source
// mà transformer được phép thay trực tiếp trong JVM.
Result process(Request request) {
    return service.handle(request);
}
~~~

Một kết quả mong muốn về mặt semantics:

~~~text
process(request):
    Agent A: incrementCallCounter()
    Agent B: startTimer()
    try:
        return originalProcess(request)
    finally:
        Agent B: recordDuration()
~~~

Đây là **mô hình khái niệm**, không phải danh sách JVM instruction. Bản implement phải giữ đúng kiểu return, operand stack, exception table, synchronized và mọi nhánh thực thi. Nếu A cũng ghi exit log hoặc B chỉ ghi metric ở normal return, **thứ tự advice** sẽ tác động kết quả đo.

| Đặc tính của method | Rủi ro khi nhiều agent sửa | Cách kiểm chứng |
| --- | --- | --- |
| **Method descriptor/overload** | Gắn advice nhầm method cùng tên | Match name + descriptor + class identity |
| **Primitive/reference return** | Sai boxing/unboxing hoặc type trên stack | Test void, primitive, object, null |
| **Exception** | Advice nuốt exception, thay cause hoặc không dọn state | Test normal/exceptional exit |
| **try/catch/finally** | Chèn branch làm sai exception table | Kiểm tra control-flow graph, handler |
| **Synchronized** | Advice thay lock order/thời gian giữ monitor | Concurrency test và thread dump |
| **Constructor** | Dùng this trước khi đối tượng hợp lệ | Kiểm tra uninitialized-this/verifier |
| **StackMapTable** | Frame không hợp lệ sau nhiều lần chèn | Verify bằng JVM và thư viện bytecode |
| **Locals/max_stack** | Hai agent cùng chiếm slot hoặc tính max sai | Đánh giá layout và recomputation |
| **Annotations/attributes** | Bỏ metadata do A hoặc framework tạo | So sánh class metadata trước/sau |
| **Helper linkage** | Bytecode mới gọi class không nhìn thấy | Test classloader/module, API visibility |

Một phép sửa đúng riêng rẽ có thể trở nên sai khi ghép với phép khác nếu B vô tình làm mất local slot, nhánh exception, hoặc metadata do A đưa vào.

### 5.1. Thứ tự onEnter/onExit cần được định nghĩa

Nếu A mở span và B mở span con, thứ tự lồng nhau ảnh hưởng mối quan hệ parent-child. Nếu B đo thời gian quanh cả method đã mang logging của A, metric có thể bao gồm chi phí log; nếu B bao quanh chỉ original body thì không. Cả hai đều có thể hợp lệ về bytecode, nhưng chỉ một cách đúng với đặc tả nghiệp vụ. Vì vậy cần test **trị số và quan hệ sự kiện**, không chỉ xác nhận JVM load class thành công.

### 5.2. Hạn chế thêm member vào lớp đã load

Một số agent muốn thêm field để lưu counter hoặc method synthetic để gọi helper. Nếu hai agent dùng cùng tên, chúng có thể xung đột ngay ở class load mới. Với **retransform/redefine**, JVM thường không cho thêm/xóa field hoặc method, đổi hierarchy và các thay đổi schema tương tự. Thay vì dựa vào field mới khi sửa lớp đã chạy, lưu state ở helper ngoài lớp hoặc dùng phương án instrumentation trong method body được JVM hỗ trợ, có chiến lược lifecycle phù hợp.

### 5.3. Mỗi agent phải giữ quyền sở hữu marker riêng

Trước khi thêm advice, A nên phát hiện **marker của A**, không xem mọi call đến helper của B là dấu hiệu “đã instrument”. Dùng identifier đủ đặc trưng, tránh field/helper names quá chung, kiểm tra cấu trúc instruction thay vì chỉ dò một tên lớp dễ trùng. Nếu không tìm được biểu diễn marker ổn định, cần có một chính sách explicit về retransform từ bytes nền tảng, không tự chèn theo cảm tính.

## 6. Module, class loader và thư viện nội bộ của hai agent

### 6.1. Hai class cùng tên không nhất thiết là một class

Kiểu runtime được phân biệt bằng **tên nhị phân + defining class loader**. Ví dụ một app server có hai bản **com.example.Service** do hai plugin loader khác nhau định nghĩa. Agent A sửa bản của plugin 1; agent B có thể sửa cả hai nếu chỉ lọc theo string tên lớp. Sự tương thích phải xét **đúng instance Class**, loader và module, không chỉ FQCN.

Nếu agent dùng cache kết quả transform theo **String className**, nó có thể đưa bytes của lớp plugin 1 vào plugin 2, gây class format/linkage lỗi hoặc hành vi bất ngờ. Cần key theo class identity phù hợp và chính sách thu hồi cache để không giữ mạnh class loader đã hết vòng đời.

### 6.2. Helper do agent A chèn phải resolve được khi method chạy

Một transform có thể thành công về mặt serialization nhưng runtime thất bại khi method mới gọi **com.agentA.Helper.enter()** và class loader của target không tìm thấy helper. Với named module, cũng cần xét **readability, exports/opens và access modifiers**. **ClassFileTransformer** chỉ tạo bytes; nó không tự giải quyết mọi quan hệ class loader/module cho code phụ trợ.

Khi nhiều agent cùng bundle ASM/Byte Buddy hoặc utility cùng FQCN nhưng khác version, có thể có **NoSuchMethodError**, **LinkageError** hoặc hành vi lệch do loader định nghĩa một bản duy nhất. Shading/relocation hoặc cách ly dependency là hướng triển khai phổ biến, song phải kiểm tra cả mã helper được tham chiếu **từ class đã transform**.

### 6.3. Không gọi tùy tiện loader.loadClass trong callback

Transformer thường chạy trong đường class loading. Nếu A đang transform X rồi gọi **loader.loadClass(Y)**, Y có thể kích hoạt B, B có thể cố load X hoặc giữ lock khác. Kết quả có thể là recursion, class circularity hoặc deadlock. Callback nên ngắn, tránh I/O blocking, lock toàn cục và dependency nặng. Nếu cần xác định common superclass khi tính frame, cần cơ chế resolution có kiểm soát thay vì eager load lớp ứng dụng ngay trong transformer.

## 7. Retransform: điểm thường làm agent tưởng đã “mất” advice

Class load ban đầu và **Instrumentation.retransformClasses(...)** không có cùng callback pattern. Theo tài liệu Java 17:

- Transformer đăng ký **canRetransform=false** được gọi ở class load/redefine, nhưng **không được gọi lại** khi retransform; JVM **tự động tái áp dụng kết quả đã lưu** từ lượt load/redefine trước của nhóm này.
- Transformer **canRetransform=true** được gọi lại ở retransform; nó phải tạo kết quả vẫn là **redefinition hợp lệ** của lớp đã chạy.
- Bytes đầu vào khi retransform có thể khác byte-for-byte so với bytes được đưa vào lúc load đầu, do constant-pool layout và attributes có thể khác.
- **Active stack frames** của method đang chạy có thể tiếp tục định nghĩa cũ, trong khi invocation mới dùng code mới. Retransform không tự chạy lại static initializer.
- Nếu kết quả bytes cuối vi phạm schema hoặc không được verifier chấp nhận, **retransformClasses** có thể ném lỗi; không thể coi log TRANSFORMED trong callback là bằng chứng hoàn tất.

~~~text
Load lần đầu:
    Original bytes → A (không hỗ trợ retransform)
                   → B (hỗ trợ retransform)
                   → installed definition

Retransform sau đó:
    JVM dựng lại bytes nền
        → tái áp dụng output đã lưu của A, KHÔNG gọi lại A
        → gọi lại B trên bytes đã qua A
        → xác minh/cài định nghĩa mới nếu hợp lệ
~~~

**Hệ quả:** B không được bỏ kết quả của A khi retransform. A cũng không thể chỉ thay cấu hình trong object của mình rồi kỳ vọng một lượt retransform sẽ gọi lại A nếu A đã đăng ký **false**. Nếu muốn tự tái cấu hình biến đổi trên lớp đã nạp, cần thiết kế capability và đường update ngay từ đầu.

### 7.1. Redefine là một con đường khác

**redefineClasses(...)** nhận các bytes định nghĩa class do caller cung cấp; các transformer áp dụng với redefine theo hợp đồng. Nó khác **retransformClasses(...)**, vốn chạy lại chuỗi từ cơ sở do JVM tái tạo và các kết quả cũ được tự động tái áp dụng theo capability. Nếu một agent redefine lớp từ bytes không tính đến agent khác, hai agent có thể tương tác khác với khi chỉ retransform.

Không dùng **removeTransformer(A)** như lệnh undo; gỡ transformer không tự hoàn nguyên bytecode đã cài. Rollback cần một kế hoạch class update đúng semantics, tương thích với các agent còn hoạt động và giới hạn schema JVM.

### 7.2. Sự kiện đồng thời và shutdown

**removeTransformer(instance)** có thể trả về trong khi một callback đã được khởi chạy trước đó vẫn chạy. Nhiều thread cũng có thể định nghĩa lớp cùng lúc. Tránh chia sẻ mutable byte[] giữa callback; nếu có cache/counter, dùng synchronization và lifecycle rõ ràng. Không đóng tài nguyên mà callback còn có thể truy cập ngay sau remove nếu chưa có giải pháp phối hợp.

## 8. Những nguyên tắc “sống chung” thực dụng

Để giảm xác suất xung đột khi hai agent cùng chỉnh một method:

1. **Chỉ sửa phạm vi cần thiết:** lọc class loader/module và name + descriptor; không blanket transform cả JDK/ứng dụng.
2. **Transform trên input hiện tại:** không dựng method từ bản gốc để ghi đè những gì agent trước đã thêm.
3. **Bảo toàn code/metadata:** dùng bytecode library có chiến lược visitor/writer được kiểm tra; tính đúng frames và exception table.
4. **Nhận diện biến đổi của chính mình:** tránh advice bị chèn lặp khi có retransform hoặc startup agent bị khai báo hai lần.
5. **Đặt tên và dependency độc lập:** không va chạm synthetic helper, static field, package hoặc thư viện dùng chung.
6. **Tối thiểu hóa side effect:** tránh gọi code ứng dụng, network, file I/O blocking hoặc lock phức tạp trong transform.
7. **Xác nhận hành vi:** không dựa duy nhất trên số callback hoặc số lần return byte[].
8. **Ghi rõ khả năng tương thích:** version A, B, JDK, app framework, cách load, module/classloader và thứ tự được hỗ trợ.

Trong một hệ thống do cùng một đội kiểm soát, **một coordinator trung tâm** có thể nhận yêu cầu từ A và B rồi tạo **một pipeline chung**; điều này hữu ích nếu phép biến đổi phụ thuộc chặt vào thứ tự hoặc chia sẻ instrumentation metadata. Với những agent bên thứ ba độc lập, không có bảo đảm mặc định rằng mọi tổ hợp/version đều tương thích; cần thử nghiệm và công bố giới hạn cụ thể.

## 9. Ma trận kiểm thử tương thích

| Kịch bản | Mục đích | Điều cần kiểm chứng |
| --- | --- | --- |
| Không agent | Baseline | Hành vi nguyên bản |
| Chỉ A | A hoạt động riêng | Metric/trace/return/exception A đúng |
| Chỉ B | B hoạt động riêng | Metric/trace/return/exception B đúng |
| A trước B | Chuỗi thứ tự 1 | B bảo toàn kết quả A; class hợp lệ |
| B trước A | Chuỗi thứ tự 2 | Kết quả và thứ tự đã được hỗ trợ |
| A xuất hiện hai lần | Idempotency | Không double advice ngoài dự kiến |
| B xuất hiện hai lần | Idempotency | Không double advice ngoài dự kiến |
| A/B khác version | Xung đột dependency | Không class shadowing/linkage lỗi |
| Load class sau premain | Coverage | Callback đúng class/loader |
| Retransform lớp đã load | Tái áp dụng | Không mất hoặc lặp advice |
| Redefine từ bản mới | Giới hạn schema | Method và metadata hợp lệ |
| Hai loader cùng class name | Scope | Đúng runtime class cần sửa |
| Method ném exception | Semantics cleanup | Không nuốt exception, dọn context |
| Concurrent class loading | Thread safety | Không race/deadlock |
| Shutdown một agent | Lifecycle | Không crash callback còn đang chạy |

### 9.1. Log cần thiết để điều tra

~~~text
Agent=A event=LOAD class=com/example/Service
loader=<identity> module=<name> method=process(Ljava/lang/String;)V
group=JAVA_NO_RETRANSFORM action=REPLACEMENT_SUPPLIED

Agent=B event=LOAD class=com/example/Service
loader=<identity> module=<name> method=process(Ljava/lang/String;)V
group=JAVA_NO_RETRANSFORM action=REPLACEMENT_SUPPLIED

Class accepted by JVM; new invocation verified; both features observed.
~~~

Đây là **mẫu log minh họa**, không phải JVM tự in. Nếu cần, ghi thêm hash của input/output để kiểm tra B có thực sự nhìn thấy bytes của A hay không. Tuy nhiên **hash khác nhau chưa chứng minh kết quả đã được JVM áp dụng**; phải kiểm tra method/hành vi của target sau khi class được định nghĩa hoặc retransformed.

Không log/copy toàn bộ classfileBuffer trong mọi lượt production nếu không cần: phí CPU, heap, tốc độ startup và dữ liệu nhạy cảm có thể tăng đáng kể.

## 10. Tình huống lỗi thường gặp và hướng sửa

| Dấu hiệu | Nguyên nhân khả dĩ | Hành động |
| --- | --- | --- |
| A đúng khi chạy riêng, A+B không còn metric A | B viết method từ bytes cũ | Dùng classfileBuffer hiện tại, kiểm tra visitor/writer |
| A+B gây VerifyError | Frame/stack/exception handler không khớp | Phân tích bytecode cuối pipeline, verifier |
| Thay thứ tự agent cho kết quả khác | Hai phép không giao hoán, hoặc nhóm khác | Kiểm tra canRetransform và order |
| Có log CHANGED nhưng runtime vẫn lỗi | Bytes cuối không hợp lệ hoặc wrong target | Kiểm tra ClassFormatError/LinkageError và class identity |
| Nhiều lần cùng một log | Advice bị chèn lặp | Kiểm tra marker/idempotency |
| Khi retransform không gọi A | A đăng ký canRetransform=false | Hiểu kết quả cũ được tự tái áp dụng, sửa chính sách capability |
| Gỡ A nhưng lời gọi vẫn chạy A | Class đã mang code A, hoặc callback đang chạy | Không coi remove là rollback; quản lý lifecycle |
| Agent mới gây NoSuchMethodError | Trùng helper/library version | Isolate/shade dependency và test |
| Chỉ một plugin gặp lỗi | Cùng FQCN nhưng loader khác | Log defining loader/module, lọc đúng |
| JVM treo lúc load class | Callback tái nhập/lock vòng | Thread dump, giảm I/O/lock trong transformer |

**Phân biệt exception từ transformer và lỗi bytecode cuối:** Theo Javadoc, khi transformer ném một exception không bắt, JVM vẫn gọi các transformer khác và thử định nghĩa lớp; với transformer đó, hiệu ứng tương tự **return null**. Nhưng nếu một transformer trả **class file không hợp lệ**, quá trình verify/define có thể thất bại. Vì vậy, không dùng throw như cách skip thông thường; **return null** khi không cần sửa.

## 11. Quy trình chẩn đoán khi agent mới làm hỏng agent cũ

Giả sử chỉ bật tracing thì đủ span; thêm profiler thì mất span. Thực hiện:

1. Xác định **class và method chính xác**, cùng defining loader/module.
2. Ghi thứ tự **nhóm transformer + thứ tự đăng ký**, không chỉ thứ tự manifest/JAR.
3. Kiểm tra A được gọi, trả bytes, và B có nhận bytes đã chứa thay đổi của A không.
4. Kiểm tra bytecode writer của B: có lấy lại bytes từ JAR, bỏ instruction, thiếu metadata hay frame sai không?
5. Xác nhận JVM đã chấp nhận định nghĩa sau chuỗi, sau đó gọi method mới để kiểm tra cả trace và profiler.
6. Kiểm tra trợ giúp runtime: helper class access, module readability, dependency version, class loader.
7. Chạy lại baseline, A, B, A+B và B+A ở đúng JDK/app build; phân loại thành xung đột thứ tự, xung đột schema, xung đột semantics hay lỗi dependency.
8. Nếu cần giao thức phối hợp, định nghĩa ownership và order rõ ràng hoặc điều phối qua một instrumentation pipeline chung.

Không kết luận “transformer B đã ghi đè A” chỉ vì log A biến mất; có thể A vẫn nằm trong bytecode nhưng helper không resolve, method không được gọi, active stack frame cũ còn chạy hoặc trace context bị xóa sai. Bằng chứng cần gắn với bước cụ thể.

## 12. Câu hỏi tự kiểm tra

1. **A trả null có hủy output B không?** Không. B có thể tiếp tục sửa.
2. **A trước B thì B nhận bytes nào?** Bytes A trả về nếu A sửa, hoặc bytes hiện có nếu A trả null.
3. **JAR A đứng trước JAR B thì transformer A luôn chạy trước?** Không nếu chúng thuộc nhóm capability khác nhau.
4. **Vì sao demo B→A cho STEP100 thay vì STEP200?** B cần tìm STEP100 nhưng chạy khi bytes còn ORIG000; B return null, A mới đổi thành STEP100.
5. **Có thể luôn đọc class file gốc từ JAR để instrument không?** Không nên; có thể xóa sửa đổi của agent trước.
6. **Tại sao phải kiểm tra exception path?** Advice của hai agent có thể đổi exception hoặc bỏ qua cleanup khi method ném lỗi.
7. **retransform có chắc gọi lại mọi transformer?** Không. Transformer canRetransform=false không được gọi lại, kết quả trước đó được tự áp dụng.
8. **removeTransformer có tự hoàn tác code đã chèn?** Không.
9. **Có thể thêm field mới vào class đã load bằng retransform như mặc định?** Không. Schema change thường bị hạn chế và cần tuân theo giới hạn JVM.
10. **Chứng minh tương thích bằng cách nào?** Bytecode cuối hợp lệ, đúng class/method, cả hai tính năng thể hiện đúng trên invocation mới trong các thứ tự/cấu hình được hỗ trợ.

## 13. Checklist trước khi phát hành

- Tôi đã biết **nhóm transformer** và thứ tự đăng ký thực tế.
- Mỗi transform xử lý **bytes hiện có**, không xóa kết quả hợp lệ trước đó.
- Mọi trường hợp không sửa dùng **return null**; mọi sửa đổi dùng **byte[] mới hợp lệ**, input bất biến.
- Phạm vi được xác định bằng **class name + defining loader/module + method descriptor** khi cần.
- Mã biến đổi giữ semantics return, exception, synchronized, stack/frame và metadata.
- Advice có cơ chế chống chèn trùng, marker riêng, không va chạm helper/dependency.
- Tôi đã thử cả **A+B** và **B+A**, đồng thời công bố thứ tự bắt buộc nếu có.
- Với lớp đã load, capability retransform/redefine, giới hạn schema và active frame đã được kiểm tra.
- Xóa transformer hoặc tắt agent được quản lý riêng, không hứa tự rollback bytes.
- Các test chính đều có **bằng chứng hành vi**, không chỉ log callback/return bytes.

## 14. Tài liệu chuẩn

- [Java SE 17 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html) — chaining, thứ tự nhóm, return null/byte[], retransform.
- [Java SE 17 — Instrumentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html) — đăng ký/gỡ transformer, capability, class retransform/redefine.
- [Java SE 17 — java.lang.instrument package specification](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html) — nhiều -javaagent và thứ tự premain.
- [Java Virtual Machine Specification SE 17 — Class File Format](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html) — constant pool, bytecode, frames và cấu trúc class file.

**Điểm cần nhớ:** tương thích giữa nhiều agent là tương thích của **chuỗi biến đổi và semantics method**. Mỗi agent nên chỉ sửa phạm vi của mình trên classfileBuffer đang có, không làm mất sửa đổi hợp lệ của các agent khác, hiểu thứ tự/capability khi retransform và xác minh hành vi thật trước khi báo thành công.
