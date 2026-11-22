# Chạy hai transformer nối tiếp và kiểm chứng thứ tự cùng ảnh hưởng của removeTransformer

## 1. Tại sao hai transformer có thể cho kết quả khác khi đảo thứ tự?

Trong Java instrumentation, một `ClassFileTransformer` không nhất thiết nhận classfile gốc trên disk. Khi nhiều transformers cùng xử lý một class, output bytes của transformer phía trước được đưa tới transformer phía sau, theo quy tắc về thứ tự callback. Nếu bước thứ hai giả định đầu vào đã chứa một marker do bước thứ nhất tạo ra, đổi thứ tự có thể làm mất hiệu lực biến đổi.

Còn một nhầm lẫn quan trọng: `Instrumentation.removeTransformer(t)` **không phải nút Undo**. Nó gỡ một đăng ký callback; class definition đã được cài trong JVM **không tự động trở lại bản trước** ngay lúc remove. Nếu cần thay definition hiện tại, bạn có thể chủ động yêu cầu `retransformClasses(...)` khi môi trường/class cho phép. Definition được tính lại theo baseline và pipeline còn hiệu lực, không phải lúc nào cũng trở về tệp class gốc.

Bài thực nghiệm trong nhóm **Thực nghiệm agent** dùng **hai transformer capable cùng nhóm** và class `demo.target.Marker` có method trả literal `BASE`. Các phép biến đổi:

~~~text
Transformer A:
    BASE -> MID1

Transformer B:
    MID1 -> DONE
~~~

Tất cả literal đều là **ASCII bốn byte**. Cùng classfile gốc, cùng hai transformer instances, nhưng:

- Đăng ký **A rồi B**: callback A nhận BASE và đổi thành MID1; callback B nhận MID1 và đổi thành DONE. Method trả `DONE`.
- Đăng ký **B rồi A**: callback B nhận BASE, không tìm MID1 nên trả `null`; callback A đổi BASE thành MID1. Method trả `MID1`.
- Gỡ B, gọi method **ngay**: method vẫn dùng definition đang cài, chưa tự đổi.
- Gỡ B rồi **retransform**: chỉ A còn tham gia, method trả MID1.
- Gỡ A, gọi method ngay: method vẫn MID1.
- Gỡ cả A/B rồi retransform: trong **lab có kiểm soát**, không còn bước nào biến đổi baseline BASE, nên method trả BASE.
- Gỡ A thêm lần nữa: `removeTransformer(A)` trả `false` vì instance A không còn đăng ký.

Ta sẽ kiểm chứng bằng cả **return value** và **log callback input/order**, không chỉ bằng suy luận.

### Học xong bạn làm được gì?

1. Dùng `Instrumentation.addTransformer` và `removeTransformer` cho đúng từng transformer instance.
2. Phân biệt **callback được gọi**, **bytes được trả về** và **class definition JVM thực thi**.
3. Hiểu `return null` nghĩa là không thay bytes ở bước đó, không phải rollback transform trước.
4. Biết thứ tự đăng ký chỉ quyết định thứ tự **trong cùng nhóm transformer**; Java/native, capable/incapable có thứ tự nhóm riêng.
5. Kiểm chứng `removeTransformer` trước/sau explicit `retransformClasses`.
6. Hiểu giá trị `true/false` từ `removeTransformer` và rủi ro đăng ký cùng instance nhiều lần.
7. Đọc đúng manifest `Can-Retransform-Classes: true`, kiểm capability và class modifiability.
8. Chạy Java 17+ để thu đủ hai bộ stdout normal/reverse đã kiểm thử.
9. Biết giới hạn của constant pool patcher demo và những điểm cần làm khác khi dùng ASM/Byte Buddy trong sản phẩm.

## 2. Quy tắc nối tiếp trong `ClassFileTransformer`

### 2.1. Chữ ký Java 17

Một transformer có thể override callback sáu tham số:

~~~java
byte[] transform(Module module, ClassLoader loader, String className,
        Class<?> classBeingRedefined, ProtectionDomain protectionDomain,
        byte[] classfileBuffer);
~~~

`className` dùng tên nội bộ với dấu `/`, ví dụ `demo/target/Marker`. `classfileBuffer` là đầu vào **ở vị trí callback hiện tại**. Một callback thường làm một trong hai việc:

- Trả `null` nếu không cần thay classfile; bytes hiện có tiếp tục sang bước tiếp.
- Trả mảng `byte[]` mới, chứa classfile hợp lệ đã biến đổi; output trở thành input của callback kế tiếp.

Mảng `classfileBuffer` **không được mutate tại chỗ**. Bộ sửa trong lab dùng `input.clone()` rồi mới thay bytes.

Ở trường hợp A→B:

~~~text
class loader / JVM: BASE
           |
           v
      A.transform
         BASE -> MID1
           |
           v
      B.transform
         MID1 -> DONE
           |
           v
JVM verify / install class definition
           |
           v
Marker.value() == "DONE"
~~~

B đảo lên trước A:

~~~text
class loader / JVM: BASE
           |
           v
      B.transform
         cần MID1 nhưng chỉ thấy BASE
         -> return null
           |
           v
      A.transform
         BASE -> MID1
           |
           v
Marker.value() == "MID1"
~~~

Hai phép biến đổi **không giao hoán**: `B(A(BASE)) = DONE`, còn `A(B(BASE)) = MID1`. Khi nhiều transformers cùng can thiệp classfile, việc giả định chúng có thể đổi chỗ tùy ý rất dễ làm mất hook hoặc tạo bytecode sai.

### 2.2. Thứ tự bốn nhóm transformer

Java SE 17 `ClassFileTransformer` chỉ rõ thứ tự:

| Nhóm | Vị trí |
|---|---:|
| Retransformation-incapable **Java** transformer | 1 |
| Retransformation-incapable **native** transformer | 2 |
| Retransformation-capable **Java** transformer | 3 |
| Retransformation-capable **native** transformer | 4 |

**Trong mỗi nhóm**, transformers được gọi theo thứ tự đăng ký. Vì bài này dùng hai transformer Java với `canRetransform=true`, cả A và B nằm cùng nhóm số 3. Do đó, chỉ cần đảo thứ tự hai lời gọi `addTransformer` sẽ đảo callback order.

Đừng diễn giải rộng thành “transformer đăng ký cuối cùng luôn chạy cuối cùng”. Nếu một transformer incapable còn transformer khác capable, JVM dùng **group order** trước registration order. Một JVMTI native transformer cũng có nhóm riêng.

### 2.3. Thứ tự khi retransform có gì khác?

`Instrumentation.retransformClasses` chạy lại transformation trên class đã nạp:

- Những transformers đăng ký `canRetransform=false` không được callback lại; JVM có thể **replay kết quả trước đây** của chúng theo Javadoc.
- Những transformers đăng ký `canRetransform=true` được gọi lại cho class đang retransform.
- Bytes cơ sở của JVM có thể không hoàn toàn giống file `.class` ban đầu theo thứ tự constant pool/attributes; cần dựa vào ngữ nghĩa API thay vì offset cố định.
- JVM chỉ kiểm tra/cài definition mới khi pipeline xử lý xong; output không hợp lệ có thể làm retransform thất bại.

Trong lab, cả A/B đều capable. Sau khi gỡ một transformer, lần `retransformClasses` mới không gọi transformer đã gỡ; chỉ callback còn đăng ký quyết định output.

### 2.4. `return null` không có nghĩa “hủy tất cả biến đổi”

Khi B chạy trước A trên input BASE, B trả null vì không thấy MID1. Điều này **không ngăn A chạy** và không có nghĩa pipeline thất bại. Tương tự, nếu B chạy sau A rồi trả null, output MID1 từ A vẫn có thể là definition sau bước B.

Điều kiện “callback đã chạy” khác với “callback đã thay bytes”. Demo log cả hai để tránh lẫn.

## 3. `removeTransformer`: hiểu đúng contract

### 3.1. Chữ ký, identity và giá trị trả về

~~~java
boolean removed = inst.removeTransformer(transformer);
~~~

Theo `Instrumentation`:

- `true` nếu instance transformer được tìm thấy và một registration bị gỡ.
- `false` nếu instance không còn được đăng ký.
- Truyền `null` gây `NullPointerException`.
- Nếu **cùng instance** được đăng ký nhiều lần, thao tác gỡ xử lý lần đăng ký khớp **gần nhất**; API khuyến nghị **không** đăng ký trùng cùng instance.
- Do callbacks có thể thực thi đồng thời trên các threads, một callback đã bắt đầu hoặc được kích hoạt có thể **vẫn diễn ra sau thao tác remove**. Remove không phải một global quiescence barrier.

API này **không trả về classfile gốc**, không gọi `redefineClasses` hoặc `retransformClasses` tự động, không dọn toàn bộ helper threads của agent, và không sửa file `Marker.class` trên disk.

### 3.2. Phân biệt ba mốc thời gian

Với normal mode đã tạo definition DONE:

~~~text
Mốc 1: class đang chạy trả DONE.
        |
        v
removeTransformer(B) => true
        |
Mốc 2: class vẫn trả DONE.
        |
        v
retransformClasses(Marker.class)
        |
       A chạy lại trên BASE, trả MID1; B không còn callback.
        |
Mốc 3: lời gọi mới tới Marker.value() trả MID1.
~~~

Sự thay đổi DONE→MID1 xảy ra **sau lần retransform**, không xảy ra ngay ở `removeTransformer(B)`.

Sau đó gỡ A: runtime vẫn MID1 cho đến khi lab retransform tiếp. Vì không còn A/B và không có transformer khác ảnh hưởng target, JVM dùng baseline tạo BASE.

**Phạm vi kết luận:** Đây là behavior của **một class lab có hai capable transformers**, không phải bảo đảm rollback cho mọi tổ hợp agents, incapable replay, redefine history hoặc active stack frames.

### 3.3. Gỡ đăng ký không hoàn nguyên side effects

Transformer bytecode đôi khi chèn code gửi metrics, logging, tracing hoặc một lời gọi helper. `removeTransformer` không thể thu hồi các events đã gửi, các side effects đã thực thi hoặc state bên ngoài JVM. Ngay cả khi một lần retransform loại bỏ lời gọi helper khỏi invocations mới, active stack frames có thể tiếp tục chạy phiên bản trước và JVM/application state vẫn tồn tại.

Vì vậy khi thiết kế shutdown hoặc rollback agent, phải có lộ trình riêng cho transformer registrations, installed code, helper resources và telemetry lifecycle.

## 4. Thiết kế oracle cho test

### 4.1. Hai transformer và trạng thái chuỗi

| ID | Input cần khớp | Output nếu khớp | Cờ |
|---|---|---|---|
| A | `BASE` | `MID1` | `canRetransform=true` |
| B | `MID1` | `DONE` | `canRetransform=true` |

Từng transformer trả null khi input không chứa đúng **một** literal cần tìm. Chúng không cần biết callback nào trước mình, chỉ phản ứng với bytes nhận được.

### 4.2. Hai lượt chạy cần tách JVM

- `normal`: ở `premain` đăng ký A trước B.
- `reverse`: ở `premain` đăng ký B trước A.

Hai run dùng cùng source `Marker.java`. Chúng phải chạy trong **hai JVM mới** để không mang theo class definition hoặc biến static/counter từ lượt trước.

### 4.3. Chỉ số cần quan sát

| Chỉ số | Vai trò |
|---|---|
| `initial` | Return value của method sau initial load |
| `initialOrder` | Thứ tự transformer callbacks và literal đầu vào |
| `initialCalls` | Số lần A/B xử lý target class |
| `removeB` | B còn đăng ký để gỡ không? |
| `afterRemoveB` | Class đã đổi ngay sau remove hay chưa? |
| `afterRetransformWithoutB` | Definition sau khi JVM chạy lại pipeline A-only |
| `retransformOrder` | Transformer thực sự được gọi ở lượt retransform đó |
| `removeA` và `afterRemoveA` | Gỡ A rồi kiểm tra immediate behavior |
| `afterRetransformWithoutBoth` | Definition khi không còn A/B, trong phạm vi lab |
| `lastOrder` | Có callback A/B nào ở lần retransform cuối không? |
| `finalCalls` | Số lượt callback sau tất cả operations |
| `removeAgainA` | Kiểm tra true/false của một instance đã bị gỡ |

Ta sẽ in order bằng `A(BASE)>B(MID1)` thay vì chỉ in labels A/B. Nhờ vậy có thể chứng minh byte array sau A thực sự trở thành input B.

## 5. Cấu trúc project Java 17+

~~~text
order-two-transformers/
├── AGENT.MF
├── src/
│   ├── agent/demo/order/OrderAgent.java
│   └── app/demo/
│       ├── target/Marker.java
│       └── app/OrderExperiment.java
└── out/                        # tạo khi build
    ├── agent/
    ├── app/
    └── order-agent.jar
~~~

Ba Java source files + một manifest; không yêu cầu Maven, Gradle, ASM, Byte Buddy hay Internet. Lab dùng một **startup agent** vì ta cần kiểm thử thứ tự biến đổi ngay tại class load; việc dùng Attach API không phải trọng tâm ở đây.

### 5.1. `src/app/demo/target/Marker.java`

~~~java
package demo.target;
public final class Marker {
    private Marker() {}
    public static String value() {
        return "BASE";
    }
}
~~~

`Marker.value()` chỉ trả một literal trong constant pool. Sau khi class được nạp qua transformers, method trả output được JVM cài đặt trong runtime. File `Marker.class` do `javac` tạo trên disk **không bị agent ghi đè**.

### 5.2. `src/agent/demo/order/OrderAgent.java` — mã hoàn chỉnh

~~~java
package demo.order;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.lang.instrument.UnmodifiableClassException;
import java.security.ProtectionDomain;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicInteger;

public final class OrderAgent {
    private static volatile Instrumentation inst;
    private static final List<String> EVENTS = new CopyOnWriteArrayList<>();
    private static final StepTransformer A = new StepTransformer("A", "BASE", "MID1");
    private static final StepTransformer B = new StepTransformer("B", "MID1", "DONE");

    private OrderAgent() {}

    public static void premain(String options, Instrumentation instrumentation) {
        inst = instrumentation;
        if (!inst.isRetransformClassesSupported()) {
            throw new IllegalStateException("Retransformation unsupported");
        }
        if ("reverse".equals(options)) {
            inst.addTransformer(B, true);
            inst.addTransformer(A, true);
        } else {
            inst.addTransformer(A, true);
            inst.addTransformer(B, true);
        }
    }

    public static String takeEvents() {
        String result = EVENTS.isEmpty() ? "none" : String.join(">", EVENTS);
        EVENTS.clear();
        return result;
    }

    public static String counts() {
        return "A=" + A.calls.get() + ",B=" + B.calls.get();
    }

    public static boolean removeA() {
        return inst.removeTransformer(A);
    }

    public static boolean removeB() {
        return inst.removeTransformer(B);
    }

    public static void retransform(Class<?> target)
            throws UnmodifiableClassException {
        if (!inst.isModifiableClass(target)) {
            throw new IllegalStateException("Unmodifiable target");
        }
        inst.retransformClasses(target);
    }

    private static final class StepTransformer implements ClassFileTransformer {
        final String label;
        final String before;
        final String after;
        final AtomicInteger calls = new AtomicInteger();

        StepTransformer(String label, String before, String after) {
            this.label = label;
            this.before = before;
            this.after = after;
        }

        @Override
        public byte[] transform(Module module, ClassLoader loader, String name,
                Class<?> classBeingRedefined, ProtectionDomain domain, byte[] bytes) {
            if (!"demo/target/Marker".equals(name)
                    || loader != ClassLoader.getSystemClassLoader()) {
                return null;
            }
            calls.incrementAndGet();
            EVENTS.add(label + "(" + stage(bytes) + ")");
            return replaceUtf8(bytes, before, after);
        }
    }

    private static String stage(byte[] bytes) {
        for (String value : new String[] {"BASE", "MID1", "DONE"}) {
            if (replaceUtf8(bytes, value, value) != null) return value;
        }
        return "unknown";
    }

    private static byte[] replaceUtf8(byte[] input, String before, String after) {
        if (input == null || input.length < 10
                || before.length() != after.length()
                || (input[0] & 255) != 0xca || (input[1] & 255) != 0xfe
                || (input[2] & 255) != 0xba || (input[3] & 255) != 0xbe) {
            return null;
        }
        byte[] output = input.clone();
        int entries = u2(input, 8), pos = 10, matches = 0;
        for (int i = 1; i < entries; i++) {
            if (pos >= input.length) return null;
            int tag = input[pos++] & 255;
            switch (tag) {
                case 1: {
                    if (pos + 2 > input.length) return null;
                    int len = u2(input, pos);
                    pos += 2;
                    if (pos + len > input.length) return null;
                    if (len == before.length()) {
                        boolean equal = true;
                        for (int j = 0; j < len; j++) {
                            if ((input[pos + j] & 255) != before.charAt(j)) {
                                equal = false;
                                break;
                            }
                        }
                        if (equal) {
                            for (int j = 0; j < len; j++) {
                                output[pos + j] = (byte) after.charAt(j);
                            }
                            matches++;
                        }
                    }
                    pos += len;
                    break;
                }
                case 3: case 4:
                case 9: case 10: case 11: case 12:
                case 17: case 18:
                    pos += 4;
                    break;
                case 5: case 6:
                    pos += 8;
                    i++;
                    break;
                case 7: case 8: case 16: case 19: case 20:
                    pos += 2;
                    break;
                case 15:
                    pos += 3;
                    break;
                default:
                    return null;
            }
            if (pos > input.length) return null;
        }
        return matches == 1 ? output : null;
    }

    private static int u2(byte[] bytes, int pos) {
        return ((bytes[pos] & 255) << 8) | (bytes[pos + 1] & 255);
    }
}
~~~

### 5.3. Giải thích mã `OrderAgent`

**Agent startup:** JVM gọi `premain` qua `-javaagent`. `Instrumentation` được JVM truyền vào, không tự khởi tạo. Kiểm tra `isRetransformClassesSupported` để không cố thực hiện các phép retransform trong JVM thiếu capability.

**Hai instance khác nhau:** A và B là hai `StepTransformer` riêng, lưu trong static fields. Chính những instance này được truyền cho `removeTransformer`; tạo instance mới có cùng nội dung không thể thay thế identity của instance đang đăng ký.

**Thứ tự có điều kiện:** `"reverse".equals(options)` đăng ký B trước A. Mặc định/`normal` đăng ký A trước B. Cả hai dùng `true` nên thuộc **cùng group Java retransformation-capable**.

**Class filter:** chỉ xử lý `demo/target/Marker` và system class loader. Internal class name dùng dấu `/`, không phải tên Java với dấu chấm. Nếu class cùng tên được nạp bởi custom loader khác, nó không được instrument trong lab.

**Event recorder:** `CopyOnWriteArrayList` để ghi `A(BASE)`, `B(MID1)` theo callback. `AtomicInteger` đếm số callback trên target. Đây là cấu trúc tiện cho kiểm thử nhỏ; không phải lựa chọn hiệu năng tối ưu cho callback tần suất cao.

**Phép `stage(...)`:** gọi `replaceUtf8(bytes, value, value)` để nhận biết một trong BASE/MID1/DONE, rồi bỏ mảng clone nếu tìm thấy. Nó thực hiện allocations phụ và chỉ phục vụ test. Khi debug production, dùng parser chỉ đọc có giới hạn.

**Phép sửa bytes:** `replaceUtf8` đi qua constant pool, chỉ thay một `CONSTANT_Utf8` phù hợp từ chuỗi bốn byte sang chuỗi bốn byte. Mảng đầu vào được giữ nguyên, output clone. Nếu không có đúng một match hoặc classfile không phù hợp, trả null.

**Giới hạn quan trọng:** đây không phải classfile parser tổng quát, không thêm instructions, không tính StackMapTable hoặc làm thay đổi class schema. Dùng thư viện bytecode/JDK Class-File API phù hợp khi làm sản phẩm.

### 5.4. `src/app/demo/app/OrderExperiment.java` — mã hoàn chỉnh

~~~java
package demo.app;

import demo.order.OrderAgent;
import demo.target.Marker;

public final class OrderExperiment {
    private OrderExperiment() {}

    public static void main(String[] args) throws Exception {
        System.out.println("initial=" + Marker.value());
        System.out.println("initialOrder=" + OrderAgent.takeEvents());
        System.out.println("initialCalls=" + OrderAgent.counts());

        System.out.println("removeB=" + OrderAgent.removeB());
        System.out.println("afterRemoveB=" + Marker.value());

        OrderAgent.retransform(Marker.class);
        System.out.println("afterRetransformWithoutB=" + Marker.value());
        System.out.println("retransformOrder=" + OrderAgent.takeEvents());
        System.out.println("afterRetransformCalls=" + OrderAgent.counts());

        System.out.println("removeA=" + OrderAgent.removeA());
        System.out.println("afterRemoveA=" + Marker.value());

        OrderAgent.retransform(Marker.class);
        System.out.println("afterRetransformWithoutBoth=" + Marker.value());
        System.out.println("lastOrder=" + OrderAgent.takeEvents());
        System.out.println("finalCalls=" + OrderAgent.counts());
        System.out.println("removeAgainA=" + OrderAgent.removeA());
    }
}
~~~

Điểm thiết yếu của `OrderExperiment`: luôn **in giá trị method ngay sau remove, trước retransform**. Nếu bỏ bước đó, ta chỉ có thể thấy kết quả sau retransform mà không chứng minh được `removeTransformer` không làm đổi definition ngay lập tức.

### 5.5. Manifest `AGENT.MF`

~~~text
Manifest-Version: 1.0
Premain-Class: demo.order.OrderAgent
Can-Retransform-Classes: true

~~~

`Premain-Class` dùng cho `-javaagent` startup; bài không dùng dynamic attach nên không cần `Agent-Class`. `Can-Retransform-Classes: true` xin capability để đăng ký `canRetransform=true` và gọi `retransformClasses`.

Nếu JVM không hỗ trợ retransformation, `isRetransformClassesSupported` trả false; nếu class cụ thể không modifiable, `isModifiableClass` trả false. Không mặc định support chỉ vì manifest có attribute.

## 6. Cách build và chạy với JDK 17+

### 6.1. Tạo output folders

Bash/Linux/macOS:

~~~bash
mkdir -p out/agent out/app
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out/agent, out/app | Out-Null
~~~

### 6.2. Biên dịch agent

~~~bash
javac --release 17 -d out/agent src/agent/demo/order/OrderAgent.java
~~~

### 6.3. Đóng agent JAR

~~~bash
jar cfm out/order-agent.jar AGENT.MF -C out/agent .
~~~

Có thể xác minh nội dung:

~~~bash
jar tf out/order-agent.jar
~~~

JAR chứa `META-INF/MANIFEST.MF` và hai classes `OrderAgent.class`, `OrderAgent$StepTransformer.class`. Agent JAR không cần đóng gói target `Marker`.

### 6.4. Biên dịch ứng dụng

~~~bash
javac --release 17 -cp out/order-agent.jar -d out/app src/app/demo/target/Marker.java src/app/demo/app/OrderExperiment.java
~~~

Ứng dụng gọi public methods của `OrderAgent` để điều khiển thí nghiệm. Vì thế agent JAR được đưa vào compile classpath và runtime classpath. Đây là **bố trí riêng của lab**, không phải yêu cầu tất yếu của mọi Java agent.

### 6.5. Chạy normal (A rồi B)

Linux/macOS:

~~~bash
java -javaagent:out/order-agent.jar=normal -cp "out/app:out/order-agent.jar" demo.app.OrderExperiment
~~~

PowerShell/Windows:

~~~powershell
java "-javaagent:out/order-agent.jar=normal" -cp "out/app;out/order-agent.jar" demo.app.OrderExperiment
~~~

### 6.6. Chạy reverse (B rồi A)

Linux/macOS:

~~~bash
java -javaagent:out/order-agent.jar=reverse -cp "out/app:out/order-agent.jar" demo.app.OrderExperiment
~~~

PowerShell/Windows:

~~~powershell
java "-javaagent:out/order-agent.jar=reverse" -cp "out/app;out/order-agent.jar" demo.app.OrderExperiment
~~~

**Quan trọng:** mỗi lệnh `java` tạo một JVM mới, do đó lần reverse không mang theo definition/counters từ lần normal. Trong source, `=normal` dùng nhánh default, `=reverse` dùng nhánh đăng ký đảo.

Dấu `:` phân cách classpath trên Unix; trên Windows dùng `;`. Java agent JAR cũng nằm trên runtime classpath chỉ vì `OrderExperiment` import `OrderAgent`.

## 7. Stdout đã kiểm chứng: normal A→B

Bản Java được biên dịch thực tế với `javac --release 17`, đóng JAR rồi chạy trên JDK 24. Stdout chính xác cho normal:

~~~text
initial=DONE
initialOrder=A(BASE)>B(MID1)
initialCalls=A=1,B=1
removeB=true
afterRemoveB=DONE
afterRetransformWithoutB=MID1
retransformOrder=A(BASE)
afterRetransformCalls=A=2,B=1
removeA=true
afterRemoveA=MID1
afterRetransformWithoutBoth=BASE
lastOrder=none
finalCalls=A=2,B=1
removeAgainA=false
~~~

### 7.1. Phân tích từng cặp kết quả

**`initial=DONE` và `initialOrder=A(BASE)>B(MID1)`**: initial load đi qua A rồi B. A nhận BASE, trả MID1; B nhận MID1, trả DONE. Lời gọi method mới thấy DONE; hai callbacks đều đúng một lần.

**`removeB=true`, `afterRemoveB=DONE`**: B đã được gỡ đăng ký nhưng definition hiện đang cài vẫn là DONE. Đây là kiểm chứng trực tiếp rằng remove không đồng nghĩa lập tức loại bỏ biến đổi đã cài.

**`afterRetransformWithoutB=MID1`, `retransformOrder=A(BASE)`**: sau lệnh `retransformClasses(Marker.class)`, chỉ A chạy, B không chạy. A bắt đầu từ baseline BASE rồi trả MID1; JVM cài definition mới. Counters trở thành A=2,B=1.

**`removeA=true`, `afterRemoveA=MID1`**: A không còn được đăng ký nhưng runtime vẫn MID1 cho đến lần retransform tiếp theo.

**`afterRetransformWithoutBoth=BASE`, `lastOrder=none`**: lần retransform cuối không gọi A/B. Trong môi trường lab không có transformer khác ảnh hưởng target, definition mới có literal BASE.

**`removeAgainA=false`**: registration của instance A đã bị gỡ. Lần gọi thứ hai không tìm được, trả false. Không thể suy từ false rằng A chưa từng instrument class.

## 8. Stdout đã kiểm chứng: reverse B→A

Chạy lệnh reverse trong **JVM mới**, nhận:

~~~text
initial=MID1
initialOrder=B(BASE)>A(BASE)
initialCalls=A=1,B=1
removeB=true
afterRemoveB=MID1
afterRetransformWithoutB=MID1
retransformOrder=A(BASE)
afterRetransformCalls=A=2,B=1
removeA=true
afterRemoveA=MID1
afterRetransformWithoutBoth=BASE
lastOrder=none
finalCalls=A=2,B=1
removeAgainA=false
~~~

### 8.1. Vì sao B(BASE) được log nhưng không tạo DONE?

B thực sự được gọi, count B tăng lên 1, nhưng input BASE không có MID1. Nó trả null. A chạy sau vẫn nhận BASE và đổi thành MID1. `initial=MID1` không phải do JVM bỏ callback B, mà vì **B không có điều kiện biến đổi** ở vị trí đầu pipeline.

### 8.2. So sánh với normal

| Mốc | Normal A→B | Reverse B→A |
|---|---|---|
| Initial value | `DONE` | `MID1` |
| Initial callbacks | `A(BASE)>B(MID1)` | `B(BASE)>A(BASE)` |
| Calls ban đầu | A=1,B=1 | A=1,B=1 |
| Remove B, giá trị ngay sau | DONE | MID1 |
| Retransform với chỉ A | MID1 | MID1 |
| Retransform order | A(BASE) | A(BASE) |
| Gỡ A, giá trị ngay sau | MID1 | MID1 |
| Retransform không còn A/B | BASE | BASE |
| Remove A lần 2 | false | false |

Kết quả này kiểm chứng **hai nội dung riêng**: thứ tự callback tạo ra output ban đầu khác nhau; `removeTransformer` không tự tính lại code đang chạy, nhưng một lần retransformation sau đó có thể thay đổi output theo pipeline còn lại.

### 8.3. Không lấy kết quả lab làm định luật rollback

Việc cuối cùng trở về BASE đúng vì:

- Input source của `Marker` ban đầu là BASE.
- Chỉ có A và B tác động target trong lab.
- Cả A và B đều capable và đã được gỡ.
- Không có redefine khác làm thay baseline.
- JVM hỗ trợ retransform, class modifiable.
- Method được gọi mới sau khi definition mới được cài.

Trong ứng dụng thật, còn incapable transforms, native tools, agents khác, class loaders và redefine history. Không có bảo đảm “gỡ cả hai thì mọi class đều trở về file JAR” trong mọi trường hợp.

## 9. Điều gì thực sự xảy ra khi retransform?

Theo Java SE 17:

~~~text
Với retransform:
    1. JVM lấy classfile base bytes phù hợp.
    2. Tái áp dụng kết quả trước của incapable transformers có liên quan.
    3. Gọi lại các capable transformers đang tham gia pipeline.
    4. Kiểm tra tính hợp lệ của classfile và cài definition mới.
~~~

Trong lab, A/B cùng capable, do đó khi còn A thì A được gọi lại, khi không còn A/B thì không ai trong lab được gọi lại. Nếu bạn thêm một transformer incapable trước load, output của nó có thể được replay mà callback không chạy, tạo kết quả khác.

**Không nhầm API:** `removeTransformer` gỡ callback; `retransformClasses` là lệnh yêu cầu JVM thay definition. Cặp thao tác có liên hệ trong thí nghiệm nhưng không phải cùng method.

### 9.1. Static fields và active frames

Retransformation không tự chạy lại `<clinit>`, không reset static fields hoặc existing objects. Nếu method đang chạy trên active stack frame khi VM retransform, frame cũ có thể tiếp tục chạy version cũ; invocation mới sử dụng definition mới.

`Marker.value()` trong lab rất ngắn, và mỗi lần kiểm tra là một invocation mới, vì vậy không cố chứng minh behavior của stack frame đang chạy giữa chừng.

### 9.2. `redefineClasses` là thao tác khác

`redefineClasses(ClassDefinition...)` nhận một bộ classfile bytes do caller cung cấp. Nó khác `retransformClasses(Class<?>...)`, vốn dựa vào baseline/pipeline của JVM. Cả hai đều bị giới hạn bởi class schema/VM capability. Không dùng kết quả của lab để tự động suy ra behavior cho một lần redefine từ bytes tùy ý.

### 9.3. Thứ tự callbacks sau khi gỡ

Trong lab, `afterRetransformCalls=A=2,B=1` có ý nghĩa:

- A được gọi 1 lần lúc load + 1 lần retransform.
- B chỉ được gọi 1 lần lúc load vì bị gỡ trước retransform.
- Một lần method invocation bình thường **không** gọi transform.
- `CopyOnWriteArrayList` chỉ chứa sự kiện mới kể từ lần `takeEvents()` trước.

Một callback không trả bytes nhưng vẫn **được tính** là callback. Một transformer có output được replay mà không gọi callback (incapable) là tình huống khác, cần phân biệt.

## 10. Không chỉ thứ tự; còn bốn vấn đề đúng đắn

### 10.1. Input của transformer B không phải source file

Nếu B là một security scanner hoặc coverage injector, nó có thể nhìn classfile **đã bị A sửa**, không phải classfile do `javac` tạo. B kiểm tra wrong stage có thể bỏ qua instrumentation, gây lỗ hổng coverage. Trong production, nên khai báo input/output contracts, marker, version và thứ tự mong muốn.

### 10.2. Trùng instrumentation khi retransform

Một capable transformer có thể được gọi lại nhiều lần. Nếu logic chỉ chèn call mà không kiểm tra marker, có thể tạo **double probes**, dẫn tới đếm metrics hai lần hoặc làm sai return/exception/side effects. Cần idempotency/normalization theo pipeline. `retransformClasses` thường bắt đầu từ baseline và replay output các incapable transformers, không phải luôn dùng đúng bytes đang chạy từ lần trước làm input.

### 10.3. Remove trong lúc callback đang chạy

`removeTransformer` có thể trả true trong khi một callback đã được kích hoạt vẫn chạy. Đừng immediately dispose state/loader/resources mà callback đang dùng mà không có synchronization phù hợp. Có thể dùng lifecycle generation, bounded queues và disable flags, nhưng không giả định remove là global stop-the-world barrier cho mọi callbacks.

### 10.4. Thay đổi class schema là giới hạn riêng

`retransformClasses` không cho tùy ý thêm/bỏ fields, methods, đổi inheritance hoặc descriptors như khi load class mới. A/B demo chỉ sửa một UTF8 literal đồng độ dài, giữ schema không đổi. Với instrumentation thật cần bytecode framework cập nhật frames/handlers/offsets và test verifier.

## 11. Hạn chế của mã patch constant pool

`replaceUtf8` là ví dụ giáo dục, không phải parser production:

- Chỉ tìm một `CONSTANT_Utf8` phù hợp bốn byte ASCII.
- Kiểm header magic `CAFEBABE`, đi qua một số tags Java classfile; không tự chứng minh mọi classfile version đều được hỗ trợ.
- Giữ nguyên chiều dài bytes và constant-pool indices.
- Trả null khi không có đúng một match.
- Không kiểm tra mọi attribute, `StackMapTable`, instruction offsets hoặc helper visibility.
- Một UTF8 constant có thể được nhiều cấu trúc classfile tham chiếu; thay bừa literal có thể gây semantics khác.
- `stage(...)` tạo clones để phát hiện literal, gây overhead bổ sung; chỉ hợp lý cho lab nhỏ.

Với ASM/Byte Buddy/JDK Class-File API, vẫn phải kiểm thử đa JDK/classloaders, constructors, synchronized methods, exception handlers, frames, records/modules và interactions giữa agents.

## 12. Khác biệt giữa hai nhóm capable và incapable

Bài chính giữ A/B cùng `canRetransform=true` để isolation thứ tự. Một biến thể:

~~~java
inst.addTransformer(A, false);
inst.addTransformer(B, true);
~~~

Lúc class load, cả A/B có thể được gọi theo group order; khi `retransformClasses`, callback A **không được gọi lại**, nhưng kết quả transform đã có của A được JVM **replay**; B được gọi lại. Điều này khác hoàn toàn với việc gỡ A khỏi registry.

Nếu bạn đăng ký A và B khác nhóm, cần áp dụng thứ tự bốn groups thay vì registration order toàn cục. Nếu đăng ký non-capable transformer **sau khi class đã load**, yêu cầu retransform **không** làm nó tự nhận callback cho class cũ.

### 12.1. Vì sao không nên tự đổi `true` thành `false` rồi dùng lại stdout?

Code `OrderExperiment` gọi retransform hai lần, và các callbacks/counters mong đợi phụ thuộc A/B capable. Nếu sửa flag của A, cả event sequence lẫn output có thể khác. Muốn thí nghiệm biến thể, tạo JVM mới và định nghĩa oracle mới, không gán stdout của phiên gốc cho mã đã thay đổi.

### 12.2. Khi nào nên chọn `true`?

Cần khi muốn chạy lại transform với class đã nạp, runtime rule updates hoặc dynamic instrumentation có kiểm soát. JVM/manifest phải hỗ trợ. `true` cũng đòi chú ý reentrancy, idempotency và class schema legality khi callback lặp lại.

`false` đủ cho các trường hợp chỉ instrument lớp load sau này, không cần callback lại khi retransform; tuy nhiên kết quả biến đổi của incapable có thể được VM replay. Đây không phải “tối ưu nhanh hơn” mặc định cho mọi workload.

## 13. Kiểm tra classfile với `javap`

Build artifact không đổi sau runtime retransform:

~~~bash
javap -c -v -classpath out/app demo.target.Marker
~~~

`javap` trên `out/app` vẫn nhìn thấy BASE, vì nó đọc file `Marker.class` do compiler tạo. Điều này **không phản bác** method runtime DONE/MID1 khi JVM đã transform definition trong memory.

Muốn kiểm tra bytes cụ thể, agent có thể chụp có chọn lọc `classfileBuffer` và bytes returned vào các file nhị phân rồi chạy:

~~~bash
javap -c -v -p captures/Marker-before.class
javap -c -v -p captures/Marker-after.class
~~~

Hai file `captures` ở trên là **ví dụ đường dẫn cho bài mở rộng**, **không** được chương trình hiện tại tạo. Trong hệ thống nhiều transformer, snapshot after của một callback cũng không mặc nhiên là VM-installed final bytes.

Cần log class internal name, defining loader, module, transform phase, checksum và run ID để tránh ghép sai snapshots hoặc lộ dữ liệu nhạy cảm.

## 14. Ma trận kiểm thử và những case dễ sai

| Case | Cách chạy | Kết quả cần có |
|---|---|---|
| 1. A→B | `=normal`, JVM mới | Initial DONE; order A(BASE)>B(MID1) |
| 2. B→A | `=reverse`, JVM mới | Initial MID1; order B(BASE)>A(BASE) |
| 3. Gỡ B, chưa retransform | Normal | DONE giữ nguyên |
| 4. Gỡ B, retransform | Normal | MID1; chỉ callback A(BASE) |
| 5. Gỡ A, chưa retransform | Cả hai mode | MID1 giữ nguyên |
| 6. Gỡ hết, retransform | Cả hai mode | BASE; lastOrder=none trong lab |
| 7. Remove A lần hai | Cả hai mode | false |
| 8. Đổi target literal | Source sửa thành chuỗi khác | Các transformers có thể return null; cập nhật oracle |
| 9. Transformer order khác nhóm | A false/B true | Cần group semantics; không áp stdout của bản gốc |
| 10. JVM không hỗ trợ retransform | Capability false | Agent fail-fast |
| 11. Class không modifiable | `isModifiableClass=false` | Từ chối retransform |
| 12. Transformer tạo bytes lỗi | Chỉ trong JVM sandbox | VM có thể từ chối với format/verify error |
| 13. Hai loaders cùng tên | Custom loader | Filter lab không chọn bản khác loader |
| 14. Remove dưới concurrency | Concurrent class definitions | Có thể còn callback đang chạy; cần synchronization |
| 15. Multiple agents | Một agent khác sửa cùng target | Kết quả có thể khác; phải xét đầy đủ pipeline |

**Không chạy fault injection trên JVM production hoặc process không có quyền.**

## 15. Chẩn đoán khi kết quả khác kỳ vọng

| Triệu chứng | Nguyên nhân có thể | Kiểm tra |
|---|---|---|
| Normal trả BASE | Agent không load, filter không khớp | Manifest, agent JAR, target class loader |
| Normal trả MID1 | B không thấy input MID1, không callback | `initialOrder`, code B, registration |
| Reverse trả DONE | Thứ tự không đảo hoặc transformer thứ ba | `options` và group/callback order |
| `initialOrder=none` | Target đã load trước khi callbacks đăng ký hoặc recorder không chọn target | Startup order, filter internal name |
| `removeB=false` | Sai instance, chưa đăng ký hoặc đã gỡ | Registration identity |
| `afterRemoveB` đổi ngay | Có thread khác retransform/redefine giữa hai lệnh | Concurrent operations, logs |
| `afterRetransformWithoutB` vẫn DONE | B vẫn tham gia, output được replay, hoặc agent khác | Group/replay/registration/pipeline |
| `afterRetransformWithoutBoth` không BASE | Còn transformer/redefine history khác hoặc lỗi | VM baseline, all agents, errors |
| `retransformOrder=none` khi A còn đăng ký | Callback không match filter hoặc không thực sự retransform | Target identity, capability |
| `removeAgainA=true` | Instance được add nhiều lần | Đếm registrations |
| `UnmodifiableClassException` | Class không sửa được | `isModifiableClass` |
| `UnsupportedOperationException` | Capability thiếu hoặc changes bị cấm | Manifest/VM support/schema |
| `ClassFormatError`, `VerifyError` | Invalid output bytes | Bytecode writer/verifier, javap |
| `NoClassDefFoundError` | Helper mà probe gọi không visible | Loader/module access |
| Sau remove còn callback log | Callback đã được kích hoạt trước gỡ | Concurrent lifecycle safeguards |

**Báo cáo sự cố nên có:** JVM/JDK, agent version, class name/loader/module, registration order/flags, event sequence, return values, call counts, first exception, classfile hashes nếu có. Không dump toàn bộ classfiles vô hạn.

## 16. Checklist triển khai thí nghiệm

### Trước build

- [ ] Dùng JDK 17+ có `java`, `javac`, `jar`.
- [ ] `AGENT.MF` có `Premain-Class` và `Can-Retransform-Classes: true`.
- [ ] Source path/package trùng tên classes.
- [ ] A và B là **hai instance riêng**, cùng `canRetransform=true`.
- [ ] Source `Marker.value()` trả đúng BASE.
- [ ] Hai mode chạy bằng hai JVM mới, không dùng một JVM có history.
- [ ] Test chỉ tác động class lab, không phải process production.

### Khi chạy normal/reverse

- [ ] Initial normal là DONE, order A(BASE)>B(MID1).
- [ ] Initial reverse là MID1, order B(BASE)>A(BASE).
- [ ] Initial counters A=1,B=1 ở cả hai mode.
- [ ] Không nhầm callback được gọi nhưng return null với "callback không chạy".

### Khi remove

- [ ] `removeB=true`, method ngay sau chưa đổi.
- [ ] Gọi explicit `retransformClasses`, chỉ A còn callback.
- [ ] A count=2,B count=1 sau retransform A-only.
- [ ] `removeA=true` và method ngay sau vẫn MID1.
- [ ] Gọi thêm retransform và quan sát BASE trong lab.
- [ ] `lastOrder=none`, `finalCalls=A=2,B=1`.
- [ ] `removeAgainA=false`.
- [ ] Không tuyên bố remove tự rollback class definition.

### Sau khi hiểu lab

- [ ] Biết cả group order lẫn registration order.
- [ ] Hiểu capable callbacks khác incapable replay.
- [ ] Hiểu active frames/static state không tự reset.
- [ ] Biết class identity theo tên + defining loader.
- [ ] Có kế hoạch lifecycle khi gỡ agent/helpers dưới concurrency.
- [ ] Có bytecode validity tests nếu áp dụng lên methods thật.
- [ ] Có chiến lược rollback riêng thay vì giả định remove là undo.

## 17. Câu hỏi ôn tập (kèm đáp án)

**1.** Vì sao normal A→B tạo DONE?

> A sửa BASE→MID1, B nhận output của A và sửa MID1→DONE.

**2.** Vì sao reverse B→A chỉ tạo MID1?

> B nhận BASE nên không tìm thấy MID1, trả null. A nhận BASE và sửa thành MID1.

**3.** B có được gọi trong reverse dù nó không thay bytes không?

> Có. `B(BASE)` trong callback log và `B=1` cho thấy B đã chạy; return null không đồng nghĩa bỏ callback.

**4.** `removeTransformer(B)` có tự đổi DONE sang MID1 không?

> Không. Nó gỡ callback, class đang cài vẫn DONE cho tới một operation thay definition phù hợp.

**5.** Điều gì làm DONE đổi thành MID1 sau khi gỡ B?

> Lần `retransformClasses(Marker.class)`, khi A còn tham gia và B đã bị gỡ.

**6.** Vì sao sau khi gỡ A rồi retransform, lab trở BASE?

> Vì không còn A/B hay transformer khác sửa target và baseline của class là BASE. Đây là kết quả có điều kiện của lab.

**7.** API `removeTransformer` trả false khi nào?

> Khi không tìm thấy registration của instance truyền vào; lab gọi gỡ A lần thứ hai được false.

**8.** Nếu đăng ký cùng instance A hai lần và remove một lần, chắc đã gỡ hết chưa?

> Không. API gỡ registration khớp gần nhất; không nên add cùng instance nhiều lần.

**9.** Registration order có quyết định toàn bộ Java/native transformers không?

> Không. Javadoc định nghĩa bốn nhóm có thứ tự cố định; trong mỗi nhóm mới dùng registration order.

**10.** `return null` có reset bytes từ transformer trước không?

> Không. Nó nói callback hiện tại không có output mới, bytes trước đó vẫn đi tiếp.

**11.** Khi retransform, incapable transformer có được gọi lại không?

> Không. Kết quả trước của transformer incapable có thể được JVM replay; capable callback được gọi lại.

**12.** Method đang chạy giữa chừng khi retransform có tự chuyển sang bytecode mới không?

> Không. Active frame có thể tiếp tục code cũ; invocations mới dùng definition mới sau install.

**13.** Vì sao `javap` trên `out/app` vẫn thấy BASE sau test?

> Vì javap đọc build artifact ở disk, không đọc definition đang được JVM chạy sau transformation.

**14.** Có thể dùng ASCII constant-pool patcher này trong production không?

> Không nên. Nó rất hẹp, không xử lý arbitrary classfiles, frames/offsets, method schema và edge cases.

**15.** Nếu thêm agent thứ ba vẫn còn transform target sau khi gỡ A/B, output cuối có nhất thiết BASE không?

> Không. Pipeline còn lại quyết định definition; không có bảo đảm rollback tổng quát.

**16.** `isRetransformClassesSupported` và `isModifiableClass` khác nhau thế nào?

> Cái đầu kiểm tra VM/manifest capability, cái sau kiểm tra class cụ thể có sửa được hay không.

**17.** Vì sao cần đo cả callback order và return value?

> Callback order chứng minh sự nối tiếp bytes; return value chứng minh JVM đã cài definition mang behavior đó.

**18.** Vì sao cần chạy normal và reverse trong hai JVM mới?

> Để class state, previous transformations và static counters không ảnh hưởng lẫn nhau.

## 18. Tài liệu chính thức

- Java SE 17, `ClassFileTransformer` — chaining output/input, nhóm thứ tự Java/native capable/incapable, return null và callback contracts: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html
- Java SE 17, `Instrumentation` — `addTransformer`, `removeTransformer`, `retransformClasses`, capability, replay và active frame behavior: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html
- Java SE 17, `java.lang.instrument` package — `Premain-Class`, `Can-Retransform-Classes` và agent manifest: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html
- Java SE 17, JVM Specification Chapter 4 — constant pool, `CONSTANT_Utf8` và classfile format: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html
- Java SE 17, `javap` — đọc build artifact và classfile snapshots: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html
