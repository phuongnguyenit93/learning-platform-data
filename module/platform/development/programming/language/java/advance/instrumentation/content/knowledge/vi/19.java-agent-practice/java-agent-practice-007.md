# So sánh kết quả của transformer có và không có khả năng retransformation

## 1. Cùng là `ClassFileTransformer`, tại sao callback lại chạy khác nhau?

Khi làm Java instrumentation, một agent có thể đăng ký `ClassFileTransformer` bằng hai cách:

~~~java
inst.addTransformer(transformer, false);
inst.addTransformer(transformer, true);
~~~

Hai cách **không chỉ khác một cờ hiệu năng**. Chúng quyết định transformer có được JVM **gọi lại** khi một class đã nạp được yêu cầu `retransformClasses(...)` hay không.

- **`canRetransform=false`:** callback được dùng cho những lượt định nghĩa class trong tương lai, cũng có thể tham gia redefine theo hợp đồng; nhưng khi `retransformClasses` chạy, JVM **không gọi lại** callback này. Với class đã được nó biến đổi ở lần load/redefine trước, JVM **tái áp dụng kết quả biến đổi đã lưu**.
- **`canRetransform=true`:** callback có thể được gọi cả ở initial load/redefine và **được gọi lại** khi `retransformClasses` thực sự chạy trên class liên quan. Nó nhận input ở vị trí trong pipeline của nó và có thể cung cấp bytes mới.
- **Transformer đăng ký sau khi class đã nạp:** nếu `canRetransform=false`, `retransformClasses` không làm callback đó tự chạy trên class cũ. Nếu transformer mới `canRetransform=true` và VM cho phép, có thể dùng `retransformClasses` để instrument class đã load.

**Điểm cần nhớ:** không được kết luận “`canRetransform=false` ⇒ biến đổi trước đó biến mất sau retransform”. Theo Java SE 17 `Instrumentation.retransformClasses`, **kết quả trước đây của transformer không capable được tái sử dụng, nhưng bản thân callback không được gọi lại**.

Bài thuộc nhóm **Thực nghiệm agent**: thay vì chỉ đọc Javadoc, chúng ta sẽ biên dịch một Java agent Java 17+, chạy một target class với giá trị gốc `ORIG`, đăng ký cả hai loại transformer, thực hiện **hai lần retransform** và quan sát **kết quả cùng số lần callback**. Sau đó đăng ký một transformer không capable **quá muộn** để kiểm tra vì sao nó không can thiệp vào class đã tồn tại.

### Mục tiêu quan sát

~~~text
Source classfile:
    Message.value() -> "ORIG"

Initial load (có agent từ startup):
    early incapable transformer: ORIG -> BASE
    capable transformer:        được gọi; trả null
    Method invocation:          "BASE"

retransformClasses lần 1:
    early incapable transformer: KHÔNG gọi lại; JVM replay bytes BASE
    capable transformer:         gọi lại; BASE -> LIVE
    Method invocation:           "LIVE"

Đăng ký late incapable sau initial load, rồi retransform lần 2:
    early incapable:              vẫn KHÔNG gọi lại
    late incapable:               KHÔNG được gọi vào class đã load
    capable:                      gọi lại, thấy BASE -> LIVE
    Method invocation:            "LIVE"
~~~

Thí nghiệm không attach động: agent được nạp **từ startup** bằng `-javaagent` để tập trung so sánh semantics của `canRetransform`. Khác biệt này cũng quan trọng khi agent được nạp bằng `agentmain`, miễn là có capability retransformation và class phù hợp. Đừng nhầm phương thức đưa agent vào JVM với chính sách gọi lại transformer.

## 2. Định nghĩa chính xác ba thời điểm

### 2.1. Initial class load

Khi JVM định nghĩa một class mới, các transformers đã đăng ký phù hợp được gọi theo thứ tự của pipeline. Mỗi transformer có thể:

1. Trả `null`: **không thay bytes** ở bước của mình.
2. Trả một `byte[]` mới: cung cấp classfile bytes thay thế để chuyển tới bước tiếp theo.
3. Ném exception: JVM có cơ chế tiếp tục xử lý các transformers khác theo hợp đồng `ClassFileTransformer`; không nên nhầm exception trong transformer với exception của hook nghiệp vụ đã chèn.

Transformer capable hay incapable đều có thể tham gia **initial class definition**. Cờ `canRetransform` không nói “chỉ transformer capable mới chạy lúc load”.

### 2.2. Retransformation của class đã nạp

Sau khi target class đã được định nghĩa, agent gọi:

~~~java
inst.retransformClasses(targetClass);
~~~

JVM thực hiện một quá trình transform lại trên class đã tồn tại. Theo Java SE 17 Javadoc, luồng cơ bản:

~~~text
initial classfile bytes / base bytes do JVM quản lý
          |
          v
Các transformer canRetransform=false:
    replay kết quả lần load/redefine trước đó
    KHÔNG gọi lại method transform(...)
          |
          v
Các transformer canRetransform=true:
    gọi lại transform(...)
          |
          v
Kiểm tra và cài đặt class definition mới
~~~

`initial classfile bytes` ở bước trên không nhất thiết byte-for-byte giống tệp `.class` trên đĩa; JVM có thể bố trí lại constant pool hoặc thuộc tính tương đương. Cơ chế replay của incapable là **tái áp dụng biến đổi trước đó** mà không yêu cầu chạy lại logic transformer.

### 2.3. Redefinition không phải retransformation

`Instrumentation.redefineClasses(ClassDefinition...)` nhận classfile bytes do caller cung cấp. `Instrumentation.retransformClasses(Class<?>...)` yêu cầu JVM chạy lại pipeline theo cơ sở bytes mà JVM quản lý. Hai hoạt động có liên hệ nhưng **khác API, khác input**.

Cờ `canRetransform=false` **không** có nghĩa transformer bị cấm mọi lần **redefine**: `addTransformer` Javadoc ghi callback được gọi khi class load hoặc redefine, nhưng chỉ khi `canRetransform=true` mới được gọi lại trong retransformation. Đừng lấy kiểm thử redefine để suy luận callback counts của retransform.

## 3. Ma trận behavior theo tình huống

| Trường hợp | Callback initial load? | Callback khi `retransformClasses`? | Điều gì xảy ra với kết quả cũ? |
|---|---|---|---|
| Đăng ký trước load, `false` | Có, nếu filter khớp | **Không** | JVM replay kết quả transform cũ |
| Đăng ký trước load, `true` | Có, nếu filter khớp | **Có** | Callback được gọi lại để quyết định output mới |
| Đăng ký **sau load**, `false` | Không có lượt load quá khứ | **Không** | Không tạo ra biến đổi mới cho class cũ chỉ nhờ retransform |
| Đăng ký **sau load**, `true` | Không có lượt load quá khứ | **Có**, nếu class/VM cho phép | Transformer có cơ hội trả bytes cho class đã load |
| `removeTransformer(t)` rồi retransform sau đó | Tùy lịch sử | Transformer đã gỡ không nhận callback tương lai theo đăng ký đó | Không coi remove là rollback class definition |
| Class không modifiable hoặc VM không hỗ trợ | Tùy lần load | Retransformation bị từ chối hoặc không thể yêu cầu | Không đo callback bằng cách giả định operation đã thành công |

**Cẩn trọng với phạm vi:** callback có thể nhận những class definitions khác (nếu không filter) hoặc các loại sự kiện khác. Bảng chỉ nói về **một class target** và yêu cầu retransformation hợp lệ. Số lần transformer được gọi cho mọi classes khác không nhất thiết là 1/2/3 như lab.

### 3.1. Cách đọc `addTransformer`

~~~java
inst.addTransformer(transformer);
~~~

tương đương:

~~~java
inst.addTransformer(transformer, false);
~~~

Vì vậy overload không có boolean **không** tự bật khả năng retransformation. Với code instrumentation muốn instrument class đã load, đây là một lỗi cấu hình hay gặp.

### 3.2. Điều kiện bắt buộc khi truyền `true`

~~~java
if (!inst.isRetransformClassesSupported()) {
    throw new IllegalStateException("Retransformation is unavailable");
}
inst.addTransformer(transformer, true);
~~~

`isRetransformClassesSupported()` cần trả `true`. Capability là tùy chọn theo JVM configuration và agent JAR: `Can-Retransform-Classes: true` trong manifest cùng hỗ trợ từ VM. Nếu unsupported, `addTransformer(..., true)` có thể ném `UnsupportedOperationException`.

Đối với class đích:

~~~java
if (!inst.isModifiableClass(targetClass)) {
    throw new IllegalStateException("Class is not modifiable");
}
~~~

Không phải mọi `Class<?>` đều có thể retransform. Cần kiểm tra cả capability chung lẫn class cụ thể.

## 4. Thiết kế thí nghiệm để phân biệt callback và kết quả

Thí nghiệm sử dụng ba transformer instances với hai kiểu behavior:

1. **EARLY (incapable, đăng ký trước class load):** ghi nhận callback; nếu gặp literal `ORIG` thì trả classfile copy có literal `BASE`. Nó không capable, nhưng thay đổi ban đầu phải vẫn được JVM replay khi retransform.
2. **CAPABLE (đăng ký trước class load):** đếm mọi callback; ở initial load quan sát `BASE` rồi trả `null`. Ở retransformation, thấy `BASE` và trả bytes có literal `LIVE`.
3. **LATE (incapable, đăng ký sau class load):** ghi nhận callback nhưng không cố sửa class. Sau hai lần retransformation, số callback của LATE **vẫn bằng 0**.

Đây không phải benchmark throughput hoặc ví dụ attach. Nó là **test về số lần callback + dữ liệu đầu vào + behavior của method**.

### 4.1. Tại sao dùng `ORIG`, `BASE`, `LIVE`?

Ba chuỗi đều là ASCII đúng **4 byte**. Transformer demo chỉ thay nội dung của một `CONSTANT_Utf8` trong constant pool, giữ length classfile, method signature, branch offsets và schema như cũ.

Cách sửa này được chọn để làm rõ **replay vs rerun**, không được khuyến nghị làm classfile patcher sản xuất. Các thay đổi bytes tùy ý có thể ảnh hưởng nhiều constant-pool references, frames, classfile format. Đối với instrumentation thực tế, dùng ASM/Byte Buddy hoặc Class-File API của JDK phù hợp.

### 4.2. Kỳ vọng chính xác

| Mốc | `Message.value()` | EARLY callbacks | CAPABLE callbacks | LATE callbacks | CAPABLE thấy BASE trong retransforms |
|---|---|---:|---:|---:|---:|
| Initial load | `BASE` | 1 | 1 | 0 | 0 |
| Sau retransform #1 | `LIVE` | 1 | 2 | 0 | 1 |
| Thêm LATE; sau retransform #2 | `LIVE` | 1 | 3 | 0 | 2 |

Kết luận từ các con số:

- EARLY callback **không tăng** từ 1 sang 2/3, nhưng ảnh hưởng `BASE` của nó vẫn nằm trong input mà CAPABLE nhận.
- CAPABLE callback **tăng** 1 → 2 → 3, chứng minh rerun ở mỗi lần retransform.
- LATE không được gọi trên target chỉ bằng `retransformClasses` khi nó không capable.
- Lần retransform #2 **không** biến `LIVE` thành một literal mới nào khác: pipeline quay lại nguồn base/replay, CAPABLE lại thấy `BASE`, sau đó đưa ra `LIVE`.
- Không đoán callback count bằng số lần `Message.value()` được gọi: method invocation **không chạy transformer**.

## 5. Java 17+ runnable: cấu trúc dự án

~~~text
compare-transformer-lab/
├── AGENT.MF
├── src/
│   ├── agent/demo/agent/CompareAgent.java
│   └── app/demo/
│       ├── target/Message.java
│       └── app/ExperimentApp.java
└── out/
    ├── agent/
    ├── app/
    └── compare-agent.jar
~~~

Có **ba Java source files** và một manifest. `CompareAgent` chứa hai lớp transformer private lồng nhau; không cần thêm source files. Ứng dụng truy cập một số method public trên agent JAR để chủ động yêu cầu retransform và lấy counts.

**Đặc điểm dùng riêng cho lab:** agent JAR vừa được nạp qua `-javaagent`, vừa nằm trên classpath của application để `ExperimentApp` gọi các method của `CompareAgent`. Đây là thiết kế giúp test nhanh trong **cùng JVM**, không phải pattern nên áp dụng mặc định cho một agent sản phẩm độc lập.

### 5.1. File `src/app/demo/target/Message.java`

~~~java
package demo.target;

public final class Message {
    private Message() {}

    public static String value() {
        return "ORIG";
    }
}
~~~

Đoạn code này là toàn bộ source class target. Nó chỉ chứa một string literal `ORIG`. Sau khi agent biến đổi classfile lúc load, ứng dụng sẽ không bao giờ thấy `ORIG` trong mốc đầu: nó thấy `BASE` vì EARLY đã sửa input trước khi class được định nghĩa.

### 5.2. File `src/app/demo/app/ExperimentApp.java`

~~~java
package demo.app;

import demo.agent.CompareAgent;
import demo.target.Message;

public final class ExperimentApp {
    private ExperimentApp() {}

    public static void main(String[] args) throws Exception {
        System.out.println("initial=" + Message.value());
        System.out.println("afterLoad=" + CompareAgent.counts());
        System.out.println("capableSawBaseAtLoad=" + CompareAgent.sawBaseAtLoad());

        CompareAgent.retransform(Message.class);
        System.out.println("afterRetransform1=" + Message.value());
        System.out.println("afterRetransform1Counts=" + CompareAgent.counts());
        System.out.println("capableSawBaseOnRetransforms="
                + CompareAgent.sawBaseOnRetransforms());

        CompareAgent.registerLateIncapable();
        CompareAgent.retransform(Message.class);
        System.out.println("afterRetransform2=" + Message.value());
        System.out.println("afterRetransform2Counts=" + CompareAgent.counts());
        System.out.println("capableSawBaseOnRetransforms="
                + CompareAgent.sawBaseOnRetransforms());
    }
}
~~~

Các lời gọi `Message.value()` không yêu cầu retransform. Hai lần biến đổi chỉ xảy ra ở **hai dòng `CompareAgent.retransform(Message.class)`**. Lần `registerLateIncapable()` nằm sau class đã load, giúp mô phỏng agent bổ sung capability sai thời điểm.

### 5.3. File `src/agent/demo/agent/CompareAgent.java`

~~~java
package demo.agent;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.lang.instrument.UnmodifiableClassException;
import java.security.ProtectionDomain;
import java.util.concurrent.atomic.AtomicInteger;

public final class CompareAgent {
    private static volatile Instrumentation instrumentation;
    private static final Incapable EARLY = new Incapable(true);
    private static final Incapable LATE = new Incapable(false);
    private static final Capable CAPABLE = new Capable();

    private CompareAgent() {}

    public static void premain(String options, Instrumentation inst) {
        instrumentation = inst;
        if (!inst.isRetransformClassesSupported()) {
            throw new IllegalStateException("Retransformation is unavailable");
        }
        inst.addTransformer(EARLY, false);
        inst.addTransformer(CAPABLE, true);
    }

    public static void retransform(Class<?> type)
            throws UnmodifiableClassException {
        Instrumentation inst = instrumentation;
        if (inst == null || !inst.isModifiableClass(type)) {
            throw new IllegalStateException(
                    "Agent is absent or class is unmodifiable");
        }
        inst.retransformClasses(type);
    }

    public static void registerLateIncapable() {
        instrumentation.addTransformer(LATE, false);
    }

    public static String counts() {
        return "early=" + EARLY.calls.get()
                + ",capable=" + CAPABLE.calls.get()
                + ",late=" + LATE.calls.get();
    }

    public static boolean sawBaseAtLoad() {
        return CAPABLE.sawBaseAtLoad;
    }

    public static int sawBaseOnRetransforms() {
        return CAPABLE.sawBaseOnRetransforms.get();
    }

    private static boolean matches(ClassLoader loader, String name) {
        return "demo/target/Message".equals(name)
                && loader == ClassLoader.getSystemClassLoader();
    }

    private static final class Incapable implements ClassFileTransformer {
        final AtomicInteger calls = new AtomicInteger();
        final boolean initialPatch;

        Incapable(boolean initialPatch) {
            this.initialPatch = initialPatch;
        }

        @Override
        public byte[] transform(Module module, ClassLoader loader, String name,
                Class<?> classBeingRedefined, ProtectionDomain pd,
                byte[] bytes) {
            if (!matches(loader, name)) return null;
            calls.incrementAndGet();
            return initialPatch ? patchUtf8(bytes, "ORIG", "BASE") : null;
        }
    }

    private static final class Capable implements ClassFileTransformer {
        final AtomicInteger calls = new AtomicInteger();
        final AtomicInteger sawBaseOnRetransforms = new AtomicInteger();
        volatile boolean sawBaseAtLoad;

        @Override
        public byte[] transform(Module module, ClassLoader loader, String name,
                Class<?> classBeingRedefined, ProtectionDomain pd,
                byte[] bytes) {
            if (!matches(loader, name)) return null;
            calls.incrementAndGet();
            boolean isRedefinition = classBeingRedefined != null;
            if (!isRedefinition) {
                sawBaseAtLoad = containsUtf8(bytes, "BASE");
                return null; // Không đổi gì ở lần class definition đầu.
            }
            byte[] result = patchUtf8(bytes, "BASE", "LIVE");
            if (result != null) sawBaseOnRetransforms.incrementAndGet();
            return result;
        }
    }

    private static int u2(byte[] b, int pos) {
        return ((b[pos] & 255) << 8) | (b[pos + 1] & 255);
    }

    private static boolean containsUtf8(byte[] classFile, String literal) {
        return patchUtf8(classFile, literal, literal) != null;
    }

    private static byte[] patchUtf8(byte[] source, String before,
            String after) {
        if (source == null || source.length < 10
                || before.length() != after.length()
                || (source[0] & 255) != 0xca
                || (source[1] & 255) != 0xfe
                || (source[2] & 255) != 0xba
                || (source[3] & 255) != 0xbe) {
            return null;
        }

        byte[] out = source.clone();
        int count = u2(source, 8);
        int pos = 10, matches = 0;

        for (int entry = 1; entry < count; entry++) {
            if (pos >= source.length) return null;
            int tag = source[pos++] & 255;
            switch (tag) {
                case 1: {
                    if (pos + 2 > source.length) return null;
                    int len = u2(source, pos);
                    pos += 2;
                    if (pos + len > source.length) return null;
                    if (len == before.length()) {
                        boolean same = true;
                        for (int i = 0; i < len; i++) {
                            if ((source[pos+i] & 255) != before.charAt(i)) {
                                same = false;
                                break;
                            }
                        }
                        if (same) {
                            for (int i = 0; i < len; i++) {
                                out[pos+i] = (byte) after.charAt(i);
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
                    entry++; // long/double chiếm hai constant pool slots.
                    break;
                case 7: case 8: case 16:
                case 19: case 20:
                    pos += 2;
                    break;
                case 15:
                    pos += 3;
                    break;
                default:
                    return null;
            }
            if (pos > source.length) return null;
        }
        return matches == 1 ? out : null;
    }
}
~~~

**Ghi chú tính runnable:** Đây là Java 17, override overload `ClassFileTransformer.transform(Module, ClassLoader, String, Class<?>, ProtectionDomain, byte[])`. Phương thức `containsUtf8` cố ý gọi `patchUtf8` với before/after giống nhau để kiểm tra **một** UTF8 entry tương ứng, nhưng không dùng output. Các transformer chỉ kiểm tra đúng `demo/target/Message` thuộc system class loader.

### 5.4. File `AGENT.MF`

~~~text
Manifest-Version: 1.0
Premain-Class: demo.agent.CompareAgent
Can-Retransform-Classes: true

~~~

`Premain-Class` dành cho agent được nạp lúc startup bằng `-javaagent`. `Can-Retransform-Classes: true` yêu cầu capability. Manifest cần newline đúng định dạng (một dòng trống kết thúc main section).

Nếu dùng dynamic attach thay vì startup, cần thiết kế thêm `Agent-Class` và `agentmain`. Bài test này **không sử dụng Attach API** để tránh trộn hai câu hỏi: “nạp agent lúc nào?” và “callback có được gọi lại khi retransform hay không?”.

## 6. Build và chạy không cần thư viện ngoài

### 6.1. Tạo output directories

Từ thư mục gốc `compare-transformer-lab`.

Linux/macOS (Bash):

~~~bash
mkdir -p out/agent out/app
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out/agent, out/app | Out-Null
~~~

### 6.2. Biên dịch agent

~~~bash
javac --release 17 -d out/agent src/agent/demo/agent/CompareAgent.java
~~~

### 6.3. Đóng JAR có manifest

~~~bash
jar cfm out/compare-agent.jar AGENT.MF -C out/agent .
~~~

Nên kiểm tra JAR:

~~~bash
jar tf out/compare-agent.jar
~~~

Phải có `META-INF/MANIFEST.MF`, `demo/agent/CompareAgent.class` và nested classes như `CompareAgent$Capable.class`, `CompareAgent$Incapable.class`. Không cần đóng gói `Message.class` vào agent JAR.

### 6.4. Biên dịch ứng dụng

~~~bash
javac --release 17 -cp out/compare-agent.jar -d out/app src/app/demo/target/Message.java src/app/demo/app/ExperimentApp.java
~~~

`ExperimentApp` import `demo.agent.CompareAgent` để chủ động retransform và đọc counters, nên agent JAR phải có ở **compile classpath** và **runtime classpath** của ứng dụng.

### 6.5. Chạy trên Linux/macOS

~~~bash
java -javaagent:out/compare-agent.jar -cp "out/app:out/compare-agent.jar" demo.app.ExperimentApp
~~~

### 6.6. Chạy trên Windows PowerShell

~~~powershell
java "-javaagent:out/compare-agent.jar" -cp "out/app;out/compare-agent.jar" demo.app.ExperimentApp
~~~

Sự khác biệt dấu `:` trên Unix và `;` trên Windows là **classpath separator**. Nếu quên `-javaagent` hoặc quên JAR ở `-cp`, thí nghiệm có thể không nhận `Instrumentation` hoặc không resolve `CompareAgent`.

**Không chạy chương trình này trong một JVM đang phục vụ nghiệp vụ thật.** `retransformClasses` thay definition runtime của class, mặc dù class được chọn trong lab rất nhỏ.

## 7. Stdout đã kiểm thử trên JVM thực tế

Bản Java source tương đương với bài đã được biên dịch bằng `javac --release 17`, đóng agent JAR và chạy trên JDK 24. Kết quả chính xác của thử nghiệm:

~~~text
initial=BASE
afterLoad=early=1,capable=1,late=0
capableSawBaseAtLoad=true
afterRetransform1=LIVE
afterRetransform1Counts=early=1,capable=2,late=0
capableSawBaseOnRetransforms=1
afterRetransform2=LIVE
afterRetransform2Counts=early=1,capable=3,late=0
capableSawBaseOnRetransforms=2
~~~

**Đây là stdout cố định từ test đã chạy**, không phải con số thời gian/throughput có thể thay đổi. Test sử dụng đúng một class target, một startup agent, một JVM, hai retransforms và những điều kiện filter đã nêu.

### 7.1. `initial=BASE` chứng minh gì?

Source method trả `ORIG`, nhưng khi JVM định nghĩa class:

1. EARLY capable=false nhận input có `ORIG` và trả bytes đổi thành `BASE`.
2. CAPABLE capable=true nhận bytes ở bước tiếp theo, thấy `BASE`, trả `null` vì đó là initial load.
3. Class được định nghĩa với method trả `BASE`.

Vì vậy `Message.value()` ban đầu trả `BASE` dù source Java là `ORIG`.

### 7.2. `afterLoad=early=1,capable=1,late=0` chứng minh gì?

EARLY và CAPABLE **đều được gọi lúc initial class load**; cờ capable không quyết định có gọi ở lần đầu. LATE chưa được đăng ký ở thời điểm này nên count=0.

### 7.3. `capableSawBaseAtLoad=true` chứng minh gì?

EARLY đã sửa bytes **trước** CAPABLE trong pipeline của demo. CAPABLE xác nhận trong constant pool có đúng một UTF8 entry `BASE`, dù source ban đầu là `ORIG`.

### 7.4. `afterRetransform1=LIVE` chứng minh gì?

Lúc gọi `retransformClasses(Message.class)` lần một:

1. EARLY `canRetransform=false` không được gọi lại. Counter vẫn = 1.
2. JVM **replay kết quả EARLY trước đó**, cho CAPABLE một đầu vào có `BASE`.
3. CAPABLE `canRetransform=true` được gọi lại, sửa `BASE` → `LIVE`.
4. JVM cài definition mới thành công; một lời gọi `Message.value()` mới trả `LIVE`.

Số callback CAPABLE tăng 1 → 2. `sawBaseOnRetransforms` tăng 0 → 1. Cả hai quan sát giải thích **vì sao method đổi LIVE nhưng EARLY không chạy lại**.

### 7.5. `afterRetransform2=LIVE` và counters 1/3/0 chứng minh gì?

Sau lần thứ nhất, chương trình đăng ký LATE với `canRetransform=false`. Khi retransform lần hai:

- EARLY vẫn không được gọi lại: **1**.
- CAPABLE được gọi thêm một lần: **3**.
- LATE không được gọi: **0**, vì nó là transformer incapable đã đăng ký sau lúc class load.
- CAPABLE tiếp tục thấy `BASE` ở đầu vào: `sawBaseOnRetransforms=2`.
- Definition cuối lại chứa `LIVE`. Hành vi ổn định, không có việc tự động xếp chồng string patch `LIVE` thêm lần nữa.

**Một cách đọc sai thường gặp:** “Transformer capable được gọi lại nên nó phải nhận bytes `LIVE` từ lượt trước”. Theo quy trình `retransformClasses`, input được xây từ baseline và các bước replay; trong demo CAPABLE nhận `BASE` ở mỗi retransform, **không** nhận định nghĩa LIVE cũ làm input duy nhất.

## 8. Cơ chế replay của incapable transformer: điểm khác biệt quan trọng nhất

### 8.1. Không gọi callback nhưng vẫn giữ tác dụng biến đổi cũ

Javadoc `Instrumentation.retransformClasses` nói rõ: với transformer đã đăng ký `canRetransform=false`, các bytes được transformer trả về trong lần load hoặc redefine gần nhất được **tái sử dụng làm output của bước ấy**, nhưng `transform(...)` **không được gọi lại**.

Ví dụ nếu EARLY thêm một lời gọi đo đạc trong bytecode ở lúc initial load, một lần retransform tương lai không tự động gỡ lời gọi ấy chỉ vì EARLY không capable. Kết quả transform trước có thể tiếp tục nằm trong definition sau retransform, phụ thuộc pipeline và các transformers khác.

Mô hình logic:

~~~text
INPUT BASELINE (ORIG)
    |
EARLY (false):
    trước load: callback ORIG -> BASE
    khi retransform: replay cùng biến đổi đã lưu
    |
CAPABLE (true):
    trước load: callback thấy BASE -> null
    khi retransform: callback thấy BASE -> LIVE
    |
OUTPUT VM: BASE ở initial load, LIVE sau retransform
~~~

### 8.2. Replay không có nghĩa gọi một hàm `transform` giả lần thứ hai

Nếu callback EARLY có side effect:

~~~java
calls.incrementAndGet();
~~~

khi retransformation xảy ra, counter **không tăng**. Số lần **tác dụng bytecode còn tồn tại** khác số lần **callback Java được thực thi**.

Với metrics, hãy dùng hai khái niệm riêng:

- **Invocation count:** lần callback được gọi.
- **Effective bytecode transformation:** ảnh hưởng transform được tái sử dụng hoặc được transformer mới trả về.

Không suy “incapable count=1” thành “biến đổi chỉ có tác dụng lần đầu rồi mất hẳn”.

### 8.3. Vì sao LATE không được gọi ở class đã load?

LATE được đăng ký sau khi class `Message` đã định nghĩa. Khi `retransformClasses` lần hai chạy, LATE không capable nên **không nhận callback**. Nó cũng không có kết quả transform cũ của class đó từ initial load để JVM replay.

Nếu LATE muốn can thiệp class đã load, cần đăng ký `canRetransform=true` và yêu cầu retransformation, nếu JVM và target class đáp ứng capability. Nếu chỉ cần instrument các class **sẽ load sau thời điểm đăng ký**, `canRetransform=false` có thể vẫn phù hợp.

### 8.4. Một transformer incapable vẫn có thể xử lý lớp mới

`canRetransform=false` không đồng nghĩa transformer “vô hiệu”. Nếu sau đó JVM định nghĩa một **class mới** khớp filter, nó vẫn có thể nhận callback initial load. Trong demo, filter cố định `demo/target/Message`, class này đã load; không phát sinh initial load mới của cùng class/loader, nên LATE luôn 0.

## 9. Thứ tự transformers và tính tương tác

### 9.1. Không đơn giản là “thứ tự đăng ký toàn cục”

Theo `ClassFileTransformer`, các transformer được tổ chức theo nhóm **retransformation-incapable/capable**, có thể có Java/native instrumentation agents. Thứ tự nhóm được JVM xác định; trong một nhóm, callbacks theo thứ tự đăng ký thích hợp.

Lab chỉ sử dụng:

~~~text
EARLY: Java transformer incapable
CAPABLE: Java transformer capable
LATE: Java transformer incapable, đăng ký sau load
~~~

Khi load target ban đầu, EARLY chạy rồi CAPABLE. LATE chưa tồn tại. Khi retransform, kết quả EARLY được replay; CAPABLE chạy lại; LATE không được gọi.

Nếu có nhiều agents/transformers ở production, hãy đọc Javadoc `ClassFileTransformer` và lưu metadata đủ để phân biệt callback/group/loader/phase. Không mặc định transformer mà bạn gọi `addTransformer` gần đây nhất sẽ chạy cuối cùng **trong mọi nhóm**.

### 9.2. Một transformer trả `null` nghĩa là gì?

`return null` có nghĩa transformer **không cung cấp bytes thay thế ở bước này**. CAPABLE trả null ở lần initial load, do đó output của EARLY là `BASE` vẫn truyền qua pipeline.

Không được hiểu `return null` là “rollback những transform trước”. Đó chỉ là “bước này không thay gì”.

### 9.3. Khi một transformer lỗi?

Javadoc cho biết JVM vẫn gọi các transformers còn lại nếu một `transform(...)` ném exception. Về logic pipeline, lỗi callback tương tự bước đó không trả bytes mới, nhưng agent nên xử lý/log lỗi đúng policy; không được báo “thành công” chỉ vì không thấy exception ở code nghiệp vụ.

Các lỗi invalid classfile sau khi pipeline hoàn thành có thể gây `ClassFormatError`, `VerifyError`, `UnsupportedOperationException` hoặc lỗi khác, tùy nguyên nhân. `retransformClasses` có thể thất bại mà không cài definition mới. Những lỗi này cần phân biệt với exception nội bộ của transformer.

### 9.4. Có nhất thiết output khi retransform phải khác không?

Không. Transformer capable có thể trả `null` hoặc trả bytes tương đương. JVM vẫn có thể thực hiện quá trình retransformation hợp lệ. Việc callback count tăng không chứng minh method behavior khác đi. Bài test dùng đồng thời:

- Counter callback.
- Kiểm tra CAPABLE thấy literal `BASE`.
- Return bytes được tạo thành công.
- Runtime invocation của `Message.value()` trả `LIVE`.

Phối hợp các bằng chứng là cách đúng để kết luận.

## 10. Retransformation và giới hạn JVM

### 10.1. Giới hạn thay đổi class schema

`retransformClasses` không phải cách thay mọi thứ trong class đã load. Các giới hạn JVM TI và Javadoc áp dụng, thường không cho phép tùy ý thêm/xóa fields hoặc methods, đổi hierarchy, đổi method descriptors hoặc class modifiers không được phép.

Lab chỉ thay một UTF8 literal cùng độ dài trong constant pool. Nó không thêm methods, fields, nhánh, stack frames hoặc exception handlers.

Nếu cần chèn method calls/hook thật, dùng bytecode library/công cụ có khả năng cập nhật StackMapTable và kiểm tra verifier; không dùng patcher ASCII cho classfile production.

### 10.2. Active stack frames

Nếu một method của class đã retransform **đang có stack frame hoạt động**, frame đó có thể tiếp tục dùng bytecode **phiên bản cũ**. Những invocation mới dùng definition mới sau khi JVM cài đặt.

Lab method `Message.value()` rất ngắn, được gọi mới ở mỗi mốc, nên không cố chứng minh code của một active frame đã nhảy sang bản mới giữa chừng.

### 10.3. Static fields và object state không reset

Retransformation không chạy lại `<clinit>` hoặc constructors của các instances đã tạo. Static fields, object instances và application state không tự được tái khởi tạo vì method code thay đổi.

Nếu có:

~~~java
static int attempts = 42;
~~~

giá trị static field không tự trở về 42 mỗi khi retransform. Phần code này là **mảnh minh họa**, không có trong `Message` của lab.

### 10.4. Cùng binary name, khác loader

Hai classes có cùng tên `demo.target.Message` nhưng được định nghĩa bởi hai class loaders khác nhau là **hai runtime classes khác nhau**. Filter trong `matches(loader, name)` cố ý kiểm tra:

~~~java
"demo/target/Message".equals(name)
        && loader == ClassLoader.getSystemClassLoader()
~~~

để tránh đụng bản class cùng tên trong custom loader. Ở application server/OSGi/plugin systems, cần quyết định rõ loader/module/layer đúng mục tiêu, không chọn theo tên đơn thuần.

### 10.5. Giá trị đo trên classfile bytes

Input `classfileBuffer` của capable transformer sau retransform không được bảo đảm byte-for-byte giống input lúc load hoặc file build artifact. JVM có thể đưa vào một representation classfile tương đương với constant pool/attributes khác; các transformers trước cũng có thể đã sửa/replay.

**Vì vậy không hardcode byte offset** để áp patch trong production. Patcher lab duyệt constant pool theo tags, không dựa vào vị trí tuyệt đối. Nhưng nó vẫn là parser hẹp, không thay một bytecode framework.

## 11. Vì sao `Can-Retransform-Classes: true` quan trọng?

Manifest của lab:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.agent.CompareAgent
Can-Retransform-Classes: true

~~~

Ở một JVM không hỗ trợ retransformation, method `isRetransformClassesSupported()` có thể trả false ngay cả khi manifest có thuộc tính này. Nếu manifest **không** cấp capability, agent không thể mặc định dùng `addTransformer(..., true)` và `retransformClasses`.

Thứ tự đúng:

~~~text
Agent JAR manifest xin capability
        |
JVM khởi tạo Instrumentation
        |
isRetransformClassesSupported() == true ?
        |-- no  -> không đăng ký capable transformer
        |-- yes -> addTransformer(t, true)
                         |
                     class đã load?
                         |
                 isModifiableClass(target)?
                         |-- no  -> dừng / báo unsupported
                         |-- yes -> retransformClasses(target)
~~~

Không bật capability bằng cách đổi boolean ở source code rồi kỳ vọng JVM tuân theo nếu manifest hoặc policy không hỗ trợ.

### 11.1. Nên dùng `false` hay `true`?

**`false`** thường hợp lý khi:

- Chỉ muốn xử lý classes **trong tương lai** lúc load hoặc trong những redefine phù hợp.
- Không yêu cầu cập nhật những classes đang chạy.
- Muốn giảm độ phức tạp của việc tự viết transform có thể lặp lại.
- JVM không có hoặc không cấp retransformation capability.

**`true`** thường cần khi:

- Muốn instrument classes **đã nạp** ở thời điểm attach/startup muộn.
- Muốn cập nhật rules/probes cho các loaded classes trong runtime.
- Muốn thay output khi retransform lại một class.
- Có mô hình idempotency/re-entrance, bytecode validity và rollback kiểm soát.

`true` không tự làm transformer “đúng hơn” hoặc luôn “nhanh hơn”; nó mở thêm đường callback và trách nhiệm thiết kế khi rerun.

### 11.2. Đăng ký sau khi class đã load

Một tình huống điển hình:

~~~text
App nạp Service lúc 08:00
Agent được attach lúc 08:30
Agent gọi addTransformer(t, false)
App tiếp tục gọi Service
Không có sự kiện load mới cho cùng Class<?> 
=> t không tự instrument Service cũ
~~~

Nếu đổi thành `addTransformer(t, true)` **và** VM cho phép, sau đó gọi `retransformClasses(Service.class)`, callback có cơ hội chạy trên lớp cũ. Chỉ attach agent và đăng ký transformer **chưa đủ** nếu không trigger retransformation.

## 12. Phân biệt retransformation với class redefinition

| Đặc điểm | `retransformClasses` | `redefineClasses` |
|---|---|---|
| Caller gửi gì? | Tập `Class<?>` đã load | Các `ClassDefinition` chứa classfile bytes |
| Nguồn bytes | JVM baseline + transform pipeline/replay | Bytes do caller cấp rồi qua pipeline tương ứng |
| Dùng để làm gì? | Reinstrument class đang chạy | Thay definition bằng classfile tùy chỉnh |
| Có thay schema tùy ý? | Không | Không, vẫn chịu giới hạn VM |
| Có chạy lại static initializer? | Không | Không |
| Active frames tự chuyển sang code mới giữa chừng? | Không | Không |
| Callback capable có thể tham gia? | Có, khi retransform | Callbacks theo contract redefine riêng |

**Không coi redefinition là “retransform không cần capability” rồi bỏ qua constraints.** Nó yêu cầu tập bytes riêng và capability tương ứng (`Can-Redefine-Classes`, `isRedefineClassesSupported()`). Test callback count ở bài này **chỉ đúng cho retransformation**, không mặc định áp dụng cho mọi `redefineClasses`.

## 13. Thay đổi nhỏ để tự nghiên cứu

Các phép thử sau có giá trị học tập khi thực hiện **từng biến thể trên một JVM lab mới**. Không nên sửa nhiều yếu tố cùng lúc rồi đoán nguyên nhân.

### 13.1. Bỏ EARLY transformer

Nếu không đăng ký EARLY, source `Message` giữ literal `ORIG`. CAPABLE chỉ tìm `BASE` nên sẽ không sửa thành `LIVE`. Khi đó lab cần **điều chỉnh oracle**: không kỳ vọng initial BASE hoặc after LIVE.

Mục tiêu của biến thể là chứng minh CAPABLE trong demo **phụ thuộc** output của EARLY. Điều đó cũng mô phỏng tình huống nhiều transformers có thứ tự/phụ thuộc bytes đầu vào.

### 13.2. Đổi CAPABLE thành `false`

Nếu `inst.addTransformer(CAPABLE, false)`, CAPABLE chỉ nhận callback initial load, trả `null` và không chạy khi retransform. Kết quả `Message.value()` còn `BASE` trong lab, nếu capability retransform có sẵn nhưng không transformer capable nào thay bytes.

**Tuy nhiên source `ExperimentApp` đang in các counters và kỳ vọng cố định của phiên bản gốc**, nên phải thay expected output khi làm biến thể. Không trình bày đó như stdout của code ban đầu.

### 13.3. Đăng ký capable transformer sau class load

Nếu CAPABLE không tồn tại ở initial load mà được đăng ký `true` sau khi `Message` đã load, rồi gọi `retransformClasses(Message.class)`, nó vẫn có thể được gọi ở retransformation, trong khi EARLY incapable replay ảnh hưởng cũ. Đây là nền tảng của việc instrument lớp đã nạp ở runtime.

Nếu đăng ký `false` sau load, `retransformClasses` **không** gọi nó. Đây chính là trường hợp LATE đã được kiểm thử.

### 13.4. Gọi retransform lần ba

Trong lab chuẩn, mỗi lần retransform hợp lệ thêm **một** callback capable. EARLY và LATE vẫn giữ counts 1 và 0. CAPABLE tiếp tục thấy input BASE và tạo LIVE, nếu JVM/pipeline vẫn đáp ứng các giả định.

Khi thêm một transformer khác hoặc thay definition bằng redefine, các source bytes và thứ tự có thể khác; không dùng quy luật số lần demo làm một bất biến toàn cục.

### 13.5. Dùng hai capable transformers cùng sửa literal

Nếu CAPABLE A đổi BASE → LIVE, CAPABLE B lại tìm BASE → DONE, B có thể **không thấy BASE** vì input của B đã bị A đổi thành LIVE. Muốn hai transformers hợp tác, phải định nghĩa rõ contracts/bytecode expectations và kiểm thử cùng pipeline.

Cần chú ý một transformer trả `null` vẫn để bytes của transformer trước chảy tiếp. Lỗi này thường xuất hiện khi ghép nhiều Java agents hoặc plugin instrumentation frameworks.

## 14. Các lỗi hay gặp khi đọc số callback

### Lỗi 1 — “`false` tức là lúc load cũng không chạy”

Sai. EARLY `false` vẫn chạy ở initial load và trả bytes BASE. Cờ chỉ quyết định **đường retransformation callback**.

### Lỗi 2 — “`false` sẽ bị xóa khỏi class khi retransform”

Sai. Kết quả trước đó của incapable transformer có thể được JVM replay, như input BASE mà CAPABLE nhìn thấy trong cả hai lần retransform.

### Lỗi 3 — “Chỉ cần addTransformer là lớp cũ được instrument”

Sai. Với class đã load, cần cơ chế retransform/redefine phù hợp; đăng ký mới không tự replay loaded classes.

### Lỗi 4 — “`true` bắt buộc transformer phải thay bytes”

Sai. Transformer capable có thể được gọi rồi trả `null` hoặc bytes tương đương. Số callback không chứng minh behavior đã đổi.

### Lỗi 5 — “CAPABLE lần hai luôn nhận LIVE vì đó là output lần trước”

Không trong demo này. JVM xây lại transformation từ base bytes và replay incapable result, nên CAPABLE thấy BASE rồi đưa ra LIVE. Input phụ thuộc pipeline và baseline, không chỉ định nghĩa đã cài trước đó.

### Lỗi 6 — “Đếm callbacks bằng số lần method được gọi”

Sai. `Message.value()` được gọi nhiều lần nhưng không trigger class transformation; chỉ class load/redefine/retransform hợp lệ mới tạo callback tương ứng.

### Lỗi 7 — “Đổi boolean `true` mà không khai manifest”

Không đủ. VM phải hỗ trợ retransformation, và JAR phải yêu cầu capability phù hợp.

### Lỗi 8 — “Cùng class name thì cùng một class”

Không. Defining class loader là một phần của runtime identity. Nếu không filter loader, metrics/callbacks có thể gộp các classes khác nhau.

### Lỗi 9 — “`removeTransformer` sẽ tự rollback tác động đã cài”

Không. Nó bỏ đăng ký callback; definition đã cài trong VM không tự quay về source gốc.

### Lỗi 10 — “Callback ném exception đồng nghĩa JVM dừng class load ngay”

Cần phân biệt hợp đồng `ClassFileTransformer`: ném exception trong transformer không nhất thiết dừng toàn bộ pipeline; những transformers khác có thể vẫn được gọi. Output classfile cuối nếu invalid vẫn có thể khiến load/retransform thất bại.

### Lỗi 11 — “Một lần retransform thành công thì mọi class đều modifiable”

Sai. `isModifiableClass` áp dụng cho từng class, và capability là tùy chọn của VM.

### Lỗi 12 — “Patcher UTF8 lab đủ dùng cho mọi classfile Java”

Sai. Nó chỉ có mục tiêu ORIG/BASE/LIVE trong class do lab kiểm soát, không hiểu mọi semantics, attributes, bytecode frames hoặc classfile versions tương lai. Cần writer/verifier chuẩn.

## 15. Khi nào cần chụp classfile before/after?

Nếu trên ứng dụng thật bạn thấy callback counts không khớp hoặc behavior khó hiểu, chụp **có chọn lọc**:

- Input `classfileBuffer` khi transformer capable được gọi.
- Mảng bytes transformer returned, nếu khác null.
- Internal class name, class loader/module, transform phase, sequence, agent version.
- SHA-256/size của binary classfile trước và sau.
- Lý do skip/filter và số lần transformer gọi.

Dùng `javap -c -v -p` đọc file đã chụp để xem constant pool, method Code, StackMapTable, exception table và references helper. Nhưng snapshot ở **một vị trí trong pipeline** không tự chứng minh JVM installed bytes cuối; nhiều transformers còn chạy sau hoặc JVM đã chuẩn hóa classfile.

Ví dụ lệnh (chỉ đúng nếu bạn đã chụp thành các file `.class`):

~~~bash
javap -c -v -p captures/Message-before.class
javap -c -v -p captures/Message-after.class
~~~

**Ví dụ của bài hiện tại không lưu các snapshot này.** Nó kiểm chứng qua counters/input markers/return value của method. Không kỳ vọng thấy thư mục `captures` sau khi chạy code nguyên bản.

## 16. Cách thiết kế transformer lặp lại an toàn

Một transformer capable có thể được gọi nhiều lần trên một loaded class; cần chú ý:

1. **Idempotency:** nếu cùng semantic input được xử lý nhiều lần, output không tăng thêm hook trùng hoặc sửa branch offsets sai.
2. **Không mutate input:** tạo output bytes mới khi thực sự thay, trả null khi bỏ qua.
3. **Giữ class schema hợp lệ:** với retransform không tùy ý đổi fields/methods/hierarchy.
4. **Không phụ thuộc input là output runtime lần trước:** JVM có baseline/replay rules.
5. **Không gắn global state tùy tiện vào object Class<?>:** tránh classloader leaks, rò tham chiếu sang plugin loaders.
6. **Lọc sớm:** theo internal class name, loader, module, retransform phase, method signature nếu cần.
7. **Reentrancy:** không instrument chính helper/logger/transformer; tránh class loading recursion.
8. **Concurrency:** callbacks có thể xảy ra từ nhiều threads; metrics và config cần visibility/synchronization đúng.
9. **Liveness:** không blocking I/O vô hạn bên trong transform; chặn time/budget nếu cần.
10. **Verification:** dùng bytecode verifier, javap, unit tests và runtime behavior tests; không báo thành công chỉ dựa trên callback invocation.

Demo `Capable` nhận cùng input BASE mỗi lần retransform và trả cùng output LIVE; đó là một dạng tính ổn định **trong phạm vi classfile đơn giản này**. Với bytecode injection thực, nên gắn marker/probe ID phù hợp để tránh nhân đôi instrumentation khi có nhiều agents.

## 17. Checklist chạy và kiểm định

### Trước khi biên dịch

- [ ] Có JDK 17+, `java`, `javac`, `jar`?
- [ ] File `AGENT.MF` có `Premain-Class` và `Can-Retransform-Classes: true`?
- [ ] Đã tách source agent/target/app cho đúng package paths?
- [ ] Target `Message` chỉ có literal `ORIG` trong method cần kiểm?
- [ ] Không chạy thí nghiệm trên JVM ngoài phạm vi được phép?

### Sau initial class load

- [ ] `initial=BASE`, không phải ORIG?
- [ ] EARLY và CAPABLE mỗi cái được gọi một lần?
- [ ] LATE chưa được đăng ký, count=0?
- [ ] CAPABLE xác nhận đã thấy BASE ở đầu vào callback initial load?
- [ ] Không đồng nhất `return null` của CAPABLE với rollback output EARLY?

### Sau retransform #1

- [ ] `isRetransformClassesSupported()` và `isModifiableClass(Message.class)` đạt?
- [ ] `afterRetransform1=LIVE`?
- [ ] EARLY counter vẫn 1?
- [ ] CAPABLE counter tăng thành 2?
- [ ] CAPABLE thấy BASE trong input retransform ít nhất một lần?
- [ ] Không gọi `Message.value()` là “transform callback”?

### Sau retransform #2 với LATE

- [ ] LATE được đăng ký sau initial load với `false`?
- [ ] `afterRetransform2=LIVE`?
- [ ] EARLY vẫn 1, CAPABLE tăng 3, LATE vẫn 0?
- [ ] CAPABLE saw BASE on retransforms = 2?
- [ ] Không suy kết quả lần hai là tiếp tục patch trực tiếp output LIVE lần một?

### Khi triển khai agent thật

- [ ] Đã hiểu thứ tự nhiều transformers và capable grouping?
- [ ] Đã đo/capture error khi retransform thất bại?
- [ ] Đã xác nhận đúng loader/module/target Class<?>?
- [ ] Có chiến lược rollback/redefine phù hợp thay vì chỉ gỡ transformer?
- [ ] Có kiểm thử active frames/static state và concurrency?
- [ ] Có bảo vệ classfile snapshots/metrics khỏi lộ dữ liệu và overhead?
- [ ] Có phân biệt callback count, bytes returned và installed runtime behavior?

## 18. Câu hỏi ôn tập có đáp án

**1.** `addTransformer(t)` tương đương `addTransformer(t, true)` hay `false`?

> Tương đương `addTransformer(t, false)`.

**2.** Vì sao EARLY `false` vẫn sửa ORIG thành BASE?

> Vì transformer incapable vẫn được gọi trong **initial class load** khi đã đăng ký trước class definition.

**3.** Sau retransform, tại sao EARLY count vẫn 1 nhưng BASE còn xuất hiện?

> Vì JVM replay **kết quả trước của EARLY** mà không gọi lại callback `transform`.

**4.** Vì sao CAPABLE count tăng từ 1 lên 3?

> Vì nó được gọi ở initial load và ở **cả hai lần** retransform do đã đăng ký `canRetransform=true`.

**5.** CAPABLE nhận chuỗi nào làm đầu vào ở mỗi retransform của demo?

> BASE, vì pipeline bắt đầu từ baseline và replay kết quả của EARLY.

**6.** LATE incapable được đăng ký sau khi target class load. Tại sao count=0 sau retransforms?

> Vì `canRetransform=false` không nhận callbacks ở retransformation, và class đó đã qua initial load trước khi LATE tồn tại.

**7.** Nếu CAPABLE trả `null` trong initial load, vì sao initial value vẫn là BASE?

> Vì null nghĩa CAPABLE không thay output từ bước trước; EARLY đã biến đổi ORIG→BASE.

**8.** Bật `canRetransform=true` trong source là đủ chưa?

> Chưa. Cần `Can-Retransform-Classes: true` trong manifest, JVM capability và class modifiable.

**9.** `retransformClasses` có được thêm method hoặc field tùy ý không?

> Không. Nó chịu các giới hạn class schema của JVM TI/Instrumentation.

**10.** `removeTransformer` có quay method về giá trị ban đầu không?

> Không. Nó gỡ đăng ký callback, không tự rollback definition runtime.

**11.** `getObjectSize` hoặc `ClassFileTransformer` có liên quan gì tới callback count trong demo?

> `ClassFileTransformer` là API chính; `getObjectSize` đo object shallow size và không liên quan đến retransform. Không dùng hai API thay cho nhau.

**12.** Nếu đổi CAPABLE thành `false`, còn điều gì khác biệt trong test?

> CAPABLE không được gọi lại khi retransform; nó chỉ trả null ở initial load, nên trong lab kết quả còn BASE, không chuyển LIVE.

**13.** Class có cùng binary name dưới custom class loader có được filter chọn không?

> Không nếu filter yêu cầu `loader == ClassLoader.getSystemClassLoader()`; class identity còn phụ thuộc defining loader.

**14.** Nếu thấy callback count tăng nhưng method vẫn trả BASE thì sao?

> Có thể transformer đã trả null hoặc input không khớp điều kiện patch. Cần kiểm tra bytes returned, log/filter, khả năng VM install và behavior test, không chỉ counter.

**15.** Khi hai transformers cùng sửa một constant pool entry, điều gì cần chú ý?

> Thứ tự pipeline và đầu vào của transformer sau. Biến đổi trước có thể khiến entry mà transformer sau tìm kiếm không còn tồn tại.

**16.** Vì sao thí nghiệm có hai lần retransform thay vì một?

> Lần hai sau khi đăng ký LATE chứng minh non-capable transformer mới không tự chạy trên class cũ; đồng thời chứng minh CAPABLE được gọi lại thêm lần nữa và luôn nhận baseline replay.

## 19. Nguồn tài liệu

- Java SE 17, `Instrumentation.addTransformer` và `retransformClasses`: sự khác biệt canRetransform, replay kết quả incapable, capable callback và giới hạn class schema: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html
- Java SE 17, `ClassFileTransformer`: thứ tự các nhóm transformer, input/output contract, returned `null`, redefinition/retransformation: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html
- Java SE 17, `java.lang.instrument` package: `Premain-Class`, `Can-Retransform-Classes`, agent manifest: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html
- Java SE 17, JVM Specification Chapter 4: classfile constant pool, `CONSTANT_Utf8`, phiên bản và attributes: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html
- OpenJDK JEP 451: các lưu ý về chính sách nạp agent động; thí nghiệm hiện tại dùng startup agent nên không cần Attach API: https://openjdk.org/jeps/451
