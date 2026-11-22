# Frame đang chạy tiếp tục dùng mã cũ; lời gọi mới dùng định nghĩa mới

## 1. Mục tiêu bài học

Khi dùng Java Instrumentation để **retransform một class đang được JVM sử dụng**, điều gì xảy ra nếu một thread đang thực thi method của class đó? JVM có chuyển stack frame đang chạy sang bytecode mới ngay lập tức hay không? Một lời gọi mới trên **chính object cũ** có còn chạy mã cũ không?

Theo hợp đồng `Instrumentation.retransformClasses` của Java SE 17:

> Nếu method bị retransformation đang có stack frame hoạt động, các frame ấy tiếp tục thực thi bytecode của phiên bản method ban đầu; những invocation mới sử dụng phiên bản method đã retransformation.

Điều này phân biệt **thay định nghĩa class cho các lời gọi sắp tới** với **thay code đang chạy dở trong một frame đã được tạo**. Retransformation **không tự khởi động lại method**, không chuyển con trỏ lệnh của frame cũ sang method mới, không gọi lại static initializer và không tạo một tập object mới.

Bài học sẽ làm rõ:

1. Stack frame hoạt động là gì và tại sao nó gắn với một phiên bản method đã được chọn.
2. Ranh giới thời gian giữa frame cũ, định nghĩa class mới và lời gọi mới.
3. Vì sao object đang sống, field và static state vẫn tồn tại qua retransformation.
4. Cách dùng `ClassFileTransformer`, `addTransformer(..., true)`, `retransformClasses` và capability từ manifest.
5. Demo **Java 17+ đầy đủ**: giữ một method đang chạy bằng `CountDownLatch`, retransform method đó, chứng minh frame cũ in `OLD` nhưng lời gọi tiếp theo trên **cùng object** in `NEW`.
6. Hệ quả cho tracing, latency, rollout instrumentation, rollback và các request đang xử lý.

**Điều kiện quan trọng:** kết luận “lời gọi mới chạy định nghĩa mới” giả định retransformation **đã thành công**, class được JVM chấp nhận và không có một lần redefinition/retransformation khác đổi định nghĩa giữa các phép đo.

## 2. Hiểu đúng “frame đang chạy” và “new invokes”

Một lời gọi method làm JVM tạo một **frame thực thi** chứa trạng thái của lời gọi ấy: local variables, operand stack và vị trí thực thi tương ứng. Method có thể đang chạy CPU, đang chờ lock, đang ngủ, chờ I/O hoặc chờ một đồng bộ khác mà frame vẫn chưa thoát.

Xem dòng thời gian:

~~~text
Thread A                                  Thread B / Instrumentation
--------                                  --------------------------
invoke Service.work() [version V1]
    |
frame A bắt đầu V1
    |
V1: làm một phần việc
    |
V1: chờ CountDownLatch   ----------------------+
    |                                          |
    |                                   addTransformer(..., true)
    |                                   retransformClasses(Service)
    |                                          |
    |                                   JVM cài definition V2
    |                                          |
frame A được đánh thức  <-----------------------+
    |
V1: tiếp tục thực thi đoạn còn lại
    |
V1: RETURN
                                         invoke Service.work() lần nữa
                                               |
                                         frame B được tạo theo V2
                                               |
                                         V2: chạy logic mới
~~~

**Không có chuyện frame A bị thay giữa chừng thành frame V2.** Nó tiếp tục phiên bản bytecode mà JVM đã chọn cho invocation A. Khi invocation B được bắt đầu sau retransformation, JVM dùng method definition mới. Đây là **ngữ nghĩa được API quy định**, không phải một mẹo của `Thread.sleep` hoặc do JVM quên cập nhật bộ nhớ.

### 2.1. “Old frame” không đồng nghĩa “old object”

Đối tượng `Service` vẫn là cùng reference trước và sau thay đổi. Một lần gọi `service.work()` đầu có thể dùng V1 và lần gọi `service.work()` tiếp theo có thể dùng V2 **trên cùng instance đó**.

Ba đại lượng cần tách bạch:

| Đối tượng theo dõi | Trước retransformation | Sau retransformation thành công |
|---|---|---|
| Object đã tạo (`service`) | Tồn tại | **Vẫn là cùng object**, không tự được cấp phát lại |
| Frame của một invocation `work()` đang hoạt động | Chạy V1 | Tiếp tục V1 đến khi frame thoát |
| Invocation `work()` bắt đầu **sau khi định nghĩa V2 đã được cài** | Chưa diễn ra | Chạy V2 |
| Static fields của class | Có giá trị hiện thời | **Được giữ nguyên**, không reset vì retransform |
| Static initializer (`<clinit>`) | Đã chạy nếu class được init | **Không tự chạy lại** |
| Constructor (`<init>`) của object cũ | Đã chạy khi tạo object | **Không tự gọi lại** |

**Ví dụ diễn giải:** một request dài đã vào `CheckoutService.process()` trước khi agent instrument. Dù bạn retransform thành công giữa request, frame xử lý request cũ có thể chạy đoạn logic cũ. Request mới đi vào method **sau** thay đổi thì chạy method mới.

### 2.2. “Lời gọi mới” là lần gọi, không phải object mới

Một hiểu nhầm thường gặp: “Mã V2 chỉ có hiệu lực với object tạo sau khi retransform.” Không đúng. **Existing instances are not affected** nghĩa là object không tự biến thành object khác, nhưng **dispatch cho method invocation mới** vẫn dùng definition mới sau retransformation.

Không nên gọi lớp được retransform là “một class khác” theo nghĩa có identity/class loader mới. Đó vẫn là cùng class identity trong JVM; định nghĩa method đã được cập nhật trong những giới hạn mà JVM cho phép.

## 3. Hợp đồng của Instrumentation.retransformClasses

API liên quan:

~~~java
Instrumentation inst; // Được JVM cung cấp cho premain/agentmain.
Class<?> target;       // Lớp đã nạp và được chọn để retransform.

if (inst.isRetransformClassesSupported()
        && inst.isModifiableClass(target)) {
    inst.retransformClasses(target);
}
~~~

Đây là **trích đoạn minh họa**, không phải chương trình chạy độc lập. Muốn có `Instrumentation`, agent phải được JVM nạp đúng cơ chế.

Để đăng ký callback cho retransformation:

~~~java
inst.addTransformer(transformer, true);
~~~

Tham số `true` nói rằng transformer này có khả năng tham gia **retransformation**. Nó chỉ được chấp nhận khi capability tương ứng được hỗ trợ. Trong main manifest của agent, thường yêu cầu:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.LiveAgent
Can-Retransform-Classes: true

~~~

Nếu agent dùng dynamic attach thì khai báo `Agent-Class` và dùng `agentmain` tương ứng, nhưng **hợp đồng frame cũ/method mới vẫn là của retransformation**, không phụ thuộc việc agent được tải trước hay sau `main`.

### 3.1. Chuyện gì xảy ra trong retransform?

Ở mức khái niệm:

1. JVM nhận danh sách class sẽ retransformation, kiểm tra capability và tính modifiable.
2. JVM xác định classfile bytes cơ sở theo quy tắc `Instrumentation`. Các bytes này **có thể không giống từng byte** với file ban đầu, ví dụ constant-pool layout/attributes có thể khác.
3. Kết quả của các transformer **không hỗ trợ retransformation** được áp lại theo hợp đồng của API, không nhất thiết gọi callback của chúng một lần nữa.
4. Các transformer **có hỗ trợ retransformation** được gọi; output từ transformer trước đi vào transformer tiếp theo theo thứ tự quy định.
5. JVM xác minh và cài những method definitions hợp lệ. Nếu lời gọi thành công, invocation mới dùng các definition đã cập nhật.
6. Các **active frames cũ** của method được thay không bị chuyển sang bytecode mới giữa chừng.

Cần **một lần gọi `retransformClasses` thực sự** để áp dụng cho lớp đã nạp. Chỉ đăng ký một transformer mới không tự cập nhật các class đã được JVM định nghĩa trước đó.

### 3.2. Nếu thao tác thất bại?

Retransformation có thể thất bại nếu VM không hỗ trợ, class không modifiable, schema mới vi phạm giới hạn, bytes sai hoặc lỗi xác minh/liên kết class. Một số lỗi liên quan gồm `UnmodifiableClassException`, `ClassFormatError`, `VerifyError`, `UnsupportedClassVersionError` hoặc lỗi theo đặc tả.

Theo Javadoc của `retransformClasses`, nếu phương thức này **ném exception/error**, **không class nào trong tập yêu cầu đã được retransform thành công**. Vì thế không được khẳng định “new invokes chạy V2” nếu không có bằng chứng thao tác thành công.

### 3.3. Những thay đổi nào được phép?

Retransformation dùng để thay đổi các phần **được JVM cho phép**, đặc biệt là method bodies, một số constant-pool entries và attributes. Không được giả định có thể tùy tiện:

- thêm hoặc xóa field;
- thêm, xóa hoặc đổi tên method;
- thay descriptor/chữ ký method;
- đổi superclass hoặc tập interfaces;
- thay cấu trúc được VM cấm sửa.

Ví dụ ở phần thực hành tạo **hai phiên bản của cùng class, cùng field/method schema**; chỉ khác nội dung method `work()`. Điều đó tránh nhầm việc thay implementation với việc tạo một kiểu object mới.

## 4. Tại sao một frame cũ còn tiếp tục được?

Frame đã bắt đầu thực thi được gắn với **phiên bản method đã dùng cho invocation đó**. Trong quá trình thay class definition, JVM có thể lưu giữ phiên bản method cũ đủ lâu cho những frame còn hoạt động. JVM TI dùng khái niệm method versions có thể trở thành **obsolete** sau khi redefinition/retransformation.

Điều này cho phép:

- Thread đang xử lý công việc không phải “quay về đầu method” chỉ vì một agent mới được bật.
- JVM không cần tự viết lại local variables và operand stack của frame để phù hợp bytecode V2.
- Việc thay đổi định nghĩa cho các lời gọi tương lai có thể diễn ra trong khi các lời gọi cũ vẫn đang hoàn tất.

**Không đồng nghĩa JVM không làm gì với JIT code.** Triển khai JVM có thể invalidate/deopt các phần mã đã JIT compile để giữ đúng ngữ nghĩa. Người dùng API chỉ nên dựa vào **hợp đồng bytecode V1 cho frame cũ, V2 cho invocation mới**, không suy đoán rằng implementation luôn giữ nguyên machine code, không có safepoint hoặc không có latency spike.

### 4.1. Frame cũ vẫn có thể gọi method mới

Một nuance quan trọng: “frame A tiếp tục bytecode V1” **không có nghĩa mọi method mà nó gọi sau đó đều dùng V1**. Nếu trong phần bytecode V1 còn lại có một lệnh **invoke một method khác** sau khi class đã được cập nhật, thì **lời gọi mới đó** được phân giải theo definition phù hợp tại thời điểm invocation.

Ví dụ, logic cũ của `process()` gọi `calculate()` sau khi vừa được đánh thức. Nếu `calculate()` đã được retransform, lần gọi `calculate()` đó có thể dùng code mới dù caller `process()` còn là frame cũ. Vì vậy, một request dài **có thể có tác động hỗn hợp giữa các method versions**, không phải snapshot đồng nhất của toàn bộ ứng dụng tại thời điểm request bắt đầu.

### 4.2. Không có replay lại sự kiện quá khứ

Nếu trước retransformation `work()` đã thực hiện 100 lần ghi dữ liệu, một probe gắn vào V2 **không thể tự quan sát lại** 100 sự kiện đó. Đối với frame cũ, một probe mới chèn ở cuối method không tự xuất hiện giữa execution frame V1. Đối với các event tương lai, agent mới có thể quan sát theo phạm vi nó thực sự instrument được.

Với tracing/metrics, phải phân biệt thời điểm **agent đã nạp**, **class đã retransform**, **frame cũ đã thoát** và **dữ liệu mới bắt đầu có hiệu lực**.

## 5. Demo hoàn chỉnh bằng Java 17+: active frame dùng OLD, lời gọi mới dùng NEW

Ví dụ dùng một agent thật với `ClassFileTransformer` và `Instrumentation.retransformClasses`. Không dùng ASM/Byte Buddy hoặc API Class-File JDK 24; toàn bộ mã biên dịch với `javac --release 17`.

Ta chuẩn bị **hai bản classfile `demo.HotMethod`**:

- **V1**: method `work()` in `OLD:entered`, tạm chờ trên `CountDownLatch`, rồi in `OLD:resumed`.
- **V2**: cùng class name, modifier và method signature, nhưng method `work()` in `NEW:invoked`.
- **Main**: tạo **một instance duy nhất**, khởi chạy thread gọi V1, đợi thread đi vào method, yêu cầu retransform V1 thành V2, giải phóng thread cũ, rồi gọi `work()` lần nữa trên **instance ban đầu**.
- **LiveAgent**: cung cấp `Instrumentation` khi `premain` và đăng ký transformer có hỗ trợ retransformation chỉ trong lúc cập nhật.

**Điểm quan trọng trong thí nghiệm:** dùng `CountDownLatch` thay vì `Thread.sleep` để tạo quan hệ thứ tự xác định. Thread cũ chỉ được đánh thức **sau khi `retransformClasses` đã trả về thành công**. Vì vậy stdout không dựa trên tốc độ máy hoặc tình huống race tình cờ.

### 5.1. Cấu trúc thư mục

~~~text
retransform-frame-lab/
├── agent.mf
├── src/
│   ├── agent/
│   │   └── demo/
│   │       └── LiveAgent.java
│   ├── app/
│   │   └── demo/
│   │       └── Main.java
│   ├── v1/
│   │   └── demo/
│   │       └── HotMethod.java
│   └── v2/
│       └── demo/
│           └── HotMethod.java
└── out/                    # tạo khi build
    ├── agent/
    ├── v1/
    ├── v2/
    └── live-agent.jar
~~~

Hai source `HotMethod.java` có **cùng tên class và cùng package** nhưng ở **hai thư mục khác nhau**. **Không biên dịch cả V1 và V2 trong cùng một lệnh/đường classpath**: cần giữ hai hiện vật riêng, để JVM khởi đầu từ V1 và transformer dùng bytes V2.

### 5.2. Agent nhận Instrumentation và yêu cầu retransform

Tệp **`src/agent/demo/LiveAgent.java`**:

~~~java
package demo;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.ProtectionDomain;

public final class LiveAgent {
    private static Instrumentation inst;

    public static void premain(
            String opts, Instrumentation instrumentation) {
        inst = instrumentation;
    }

    public static void update(
            Class<?> target, Path replacement) throws Exception {
        if (!inst.isRetransformClassesSupported()
                || !inst.isModifiableClass(target)) {
            throw new IllegalStateException(
                    "Retransformation unavailable");
        }

        byte[] bytes = Files.readAllBytes(replacement);

        ClassFileTransformer tx = new ClassFileTransformer() {
            @Override
            public byte[] transform(
                    ClassLoader loader,
                    String name,
                    Class<?> redefining,
                    ProtectionDomain protection,
                    byte[] input) {

                if ("demo/HotMethod".equals(name)
                        && target == redefining) {
                    System.out.println("agent:transform");
                    return bytes;
                }
                return null;
            }
        };

        inst.addTransformer(tx, true);
        try {
            inst.retransformClasses(target);
        } finally {
            inst.removeTransformer(tx);
        }
    }
}
~~~

**Giải thích chi tiết:**

- JVM truyền `Instrumentation` cho `premain` trong startup agent. Ta giữ nó ở trường tĩnh để `Main` có thể yêu cầu retransformation **trong lúc ứng dụng đang chạy**.
- `isRetransformClassesSupported()` kiểm tra capability (cần manifest phù hợp và VM hỗ trợ); `isModifiableClass(target)` kiểm tra class cụ thể.
- `Files.readAllBytes(replacement)` đọc **class file V2** đã biên dịch. Đây là demo dùng file local tin cậy; production cần kiểm soát nguồn/định dạng/signature của bytecode.
- Trong `transform`, `name` sử dụng tên nội bộ JVM `demo/HotMethod`. `redefining` là class đang được retransform, giúp lọc chính xác target đang tồn tại; với việc định nghĩa class mới, tham số này thường là `null`.
- `return bytes` là **byte[] của định nghĩa thay thế**. Không chèn dữ liệu vào `input` tại chỗ; các bytes được trình cho JVM xác minh và áp dụng.
- `addTransformer(tx, true)` là yêu cầu để callback mới được gọi khi `retransformClasses` chạy.
- `try/finally` luôn gỡ transformer sau thao tác. **Gỡ transformer không tự hoàn nguyên definition đã cài.** Một lần retransform về sau có thể tái áp dụng chuỗi transformer khác và cho ra định nghĩa khác; không coi trạng thái là bất biến vĩnh viễn.

**Lưu ý:** Demo dùng agent nạp **lúc startup** rồi yêu cầu retransform **sau khi method đã hoạt động**. Bài đang kiểm tra hành vi **retransformation**, không kiểm tra cơ chế dynamic attach. Một agent được attach muộn bằng `agentmain` cũng có thể yêu cầu retransformation nếu JVM cho phép và agent có capability tương ứng.

### 5.3. Main điều khiển đồng bộ giữa hai thread

Tệp **`src/app/demo/Main.java`**:

~~~java
package demo;

import java.nio.file.Path;
import java.util.concurrent.CountDownLatch;

public final class Main {
    static final CountDownLatch ENTERED = new CountDownLatch(1);
    static final CountDownLatch RELEASE = new CountDownLatch(1);

    public static void main(String[] args) throws Exception {
        HotMethod service = new HotMethod();

        Thread worker = new Thread(service::work, "old-frame");
        worker.start();

        ENTERED.await();
        System.out.println("main:before-retransform");

        try {
            LiveAgent.update(
                    HotMethod.class, Path.of(args[0]));
            System.out.println("main:after-retransform");
        } finally {
            RELEASE.countDown();
            worker.join();
        }

        service.work();
    }
}
~~~

**Vì sao có hai latch?**

- `ENTERED` giúp thread main biết thread worker **đã vào V1.work()** và đang trên đường tới vị trí chờ, trước khi bắt đầu retransform. Không cần đoán với thời gian ngủ.
- `RELEASE` chặn không cho frame cũ hoàn tất trước thời điểm update. Thread main chỉ mở latch sau khi `LiveAgent.update` đã trả về (dù update thất bại thì `finally` vẫn giải phóng worker, tránh treo demo).
- `worker.join()` bảo đảm frame cũ đã thoát trước khi main tạo invocation tiếp theo. Điều này giữ **stdout có thứ tự xác định**.
- `service` là **một object được cấp phát đúng một lần**; không có lệnh `new HotMethod()` thứ hai. Đây là chứng minh rằng **một instance cũ vẫn sử dụng method definition mới trong invocation sau**.
- `Path.of(args[0])` nhận đường dẫn classfile V2 từ dòng lệnh. Phải cung cấp đúng một đối số như lệnh ở mục 5.7.

### 5.4. Phiên bản V1: method đang hoạt động

Tệp **`src/v1/demo/HotMethod.java`**:

~~~java
package demo;

public final class HotMethod {
    public void work() {
        System.out.println("OLD:entered");
        Main.ENTERED.countDown();

        try {
            Main.RELEASE.await();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return;
        }

        System.out.println("OLD:resumed");
    }
}
~~~

Khi thread worker gọi `work()`:

1. Nó in `OLD:entered`.
2. Nó báo cho main rằng đã đi vào method.
3. Nó chờ `Main.RELEASE.await()` nhưng **frame của `work()` vẫn đang hoạt động**, chưa return.
4. Khi main mở latch, nó tiếp tục đến lệnh in `OLD:resumed` trong **bytecode V1**.

Nếu method V1 bị retransform giữa bước 3 và 4, frame này **không tự chuyển sang V2**.

### 5.5. Phiên bản V2: method dùng cho các invocation mới

Tệp **`src/v2/demo/HotMethod.java`**:

~~~java
package demo;

public final class HotMethod {
    public void work() {
        System.out.println("NEW:invoked");
    }
}
~~~

Hai source dùng cùng `package demo`, cùng tên binary `demo.HotMethod`, cùng modifiers, constructor mặc định tương thích, cùng instance method `public void work()` và **không thêm field/method mới**. Chỉ method body thay đổi, nên đây là trường hợp điển hình phù hợp với giới hạn retransformation trên JVM hỗ trợ.

`NEW:invoked` được in trong invocation **sau** khi định nghĩa V2 đã được cài. Nó không phải log do transformer tự in; transformer in một dòng riêng `agent:transform`.

### 5.6. Manifest và lệnh build

Tệp **`agent.mf`**:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.LiveAgent
Can-Retransform-Classes: true

~~~

Giữ newline ở cuối tệp. `Can-Retransform-Classes: true` **yêu cầu** quyền retransform; nếu JVM không hỗ trợ, `isRetransformClassesSupported()` có thể false. Không cần `Can-Redefine-Classes` vì demo không gọi `redefineClasses`.

Tạo thư mục build với Bash:

~~~bash
mkdir -p out/agent out/v1 out/v2
~~~

Hoặc PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out/agent, out/v1, out/v2
~~~

Tại gốc `retransform-frame-lab`, biên dịch bằng **JDK 17 trở lên**:

~~~bash
javac --release 17 -d out/agent src/agent/demo/LiveAgent.java
javac --release 17 -cp out/agent -d out/v1 src/v1/demo/HotMethod.java src/app/demo/Main.java
javac --release 17 -d out/v2 src/v2/demo/HotMethod.java
jar --create --file out/live-agent.jar --manifest agent.mf -C out/agent .
~~~

**Giải thích thứ tự build:**

1. Agent phải được biên dịch trước để main có thể import/biết lớp `demo.LiveAgent`.
2. `Main` và **HotMethod V1** được biên dịch chung vào `out/v1`; code V1 tham chiếu `Main.ENTERED`/`Main.RELEASE`.
3. **HotMethod V2** được biên dịch **riêng** vào `out/v2`. Không cho `out/v2` vào classpath ứng dụng lúc khởi động.
4. JAR agent chứa `LiveAgent.class` và `META-INF/MANIFEST.MF`, nhưng không chứa bản V1/V2 của `HotMethod`.
5. `-javaagent` lúc chạy tự nạp agent; main có thể gọi vào `LiveAgent` được nạp trong system class loader theo cơ chế startup agent JAR.

**Kiểm tra artifacts:**

~~~bash
jar --list --file out/live-agent.jar
javap -verbose -classpath out/v1 demo.HotMethod
javap -verbose -classpath out/v2 demo.HotMethod
~~~

Trong cả hai output của `javap`, với `--release 17`, tìm `major version: 61`. Có thể dùng `javap -p -s` để kiểm tra cả hai có method descriptor `()V` cho `work`. Class V2 là **định nghĩa thay thế cùng class**, không phải class với tên/package mới.

### 5.7. Chạy bài thực hành

~~~bash
java -Xverify:all -javaagent:out/live-agent.jar -cp out/v1 demo.Main out/v2/demo/HotMethod.class
~~~

Các phần của lệnh:

- `-Xverify:all` yêu cầu JVM thực hiện verification đầy đủ hơn trong môi trường thử nghiệm.
- `-javaagent:out/live-agent.jar` nạp agent khi JVM startup, để lấy `Instrumentation`.
- `-cp out/v1` cung cấp `Main` và **class V1** của ứng dụng.
- `out/v2/demo/HotMethod.class` là **đường dẫn tới class bytes V2**, được `LiveAgent.update` đọc khi gọi retransformation.

**Stdout của demo trên JVM hỗ trợ retransformation:**

~~~text
OLD:entered
main:before-retransform
agent:transform
main:after-retransform
OLD:resumed
NEW:invoked
~~~

Ví dụ này đã được kiểm thử trên JDK có hỗ trợ Java 17 target, với `javac --release 17` và `java -Xverify:all`.

### 5.8. Vì sao sáu dòng này chứng minh điều cần học?

| Dòng | Ai in? | Ý nghĩa |
|---|---|---|
| `OLD:entered` | Worker, method V1 | Invocation cũ đã bắt đầu |
| `main:before-retransform` | Main | Worker đã vào method, giờ bắt đầu thay definition |
| `agent:transform` | Agent callback | JVM đã gọi transformer đúng class khi retransform |
| `main:after-retransform` | Main | `retransformClasses` trả về bình thường, V2 được chấp nhận |
| `OLD:resumed` | **Frame worker cũ** | Frame đã hoạt động từ trước vẫn đi tiếp trong bytecode V1 |
| `NEW:invoked` | **Invocation mới trên cùng service** | Method body V2 được dùng cho lần gọi tiếp theo |

Đây **không phải** hai object khác nhau. Không có code tạo object thứ hai sau retransformation. Chúng là **hai invocation của cùng method name trên cùng instance**, bắt đầu ở hai thời điểm khác nhau.

**Điểm cần phân biệt:** Output `agent:transform` chỉ chứng minh callback chạy. Chính việc `retransformClasses` trở về thành công **và** invocation mới in `NEW:invoked` mới chứng minh definition V2 đã được cài và sử dụng.

## 6. Tương tác giữa nhiều frame, thread và method versions

### 6.1. Hai frame của cùng method có thể đồng thời dùng hai versions

Trong demo, ta cho frame cũ thoát rồi mới gọi method mới để stdout dễ hiểu. Nhưng về mặt ngữ nghĩa, nếu sau khi `retransformClasses` thành công, **main gọi `service.work()` khi worker cũ vẫn đang chờ**, JVM có thể có đồng thời:

~~~text
Thread worker: work() frame từ trước -> bytecode V1 (đang chờ)
Thread main:   work() invocation mới -> bytecode V2 (chạy)
~~~

Điều này không đòi hai `ClassLoader`, hai `Class` objects hoặc hai instance. **Method-version coexistence** là điều bình thường trong giai đoạn chuyển đổi.

Nếu muốn thử, chuyển lời gọi `service.work()` trong `Main` vào **ngay sau** dòng `main:after-retransform` nhưng **trước** `RELEASE.countDown()`. Trong V2 demo, method mới chỉ in một dòng nên không chặn. Hãy chạy lại trong môi trường thử nghiệm để quan sát `NEW:invoked` khi worker cũ chưa thoát.

### 6.2. Một lời gọi dài có thể còn sống sau nhiều lần retransform

Một frame đã bắt đầu với V1 có thể giữ ngữ nghĩa V1 dù class được retransform sang V2 rồi V3, miễn là frame đó vẫn hoạt động và VM áp dụng những bản thay đổi hợp lệ. Lời gọi mới sau mỗi lần thay definition sẽ dùng version tương ứng tại thời điểm invocation.

**Không suy diễn rằng việc chuyển đổi ngữ nghĩa toàn hệ thống là tức thời.** Tại một thời điểm có thể có:

- request cũ trong frame V1;
- request khởi chạy sau update thứ nhất dùng V2;
- request mới hơn dùng V3;
- tài nguyên chung (database, queues, static state) vẫn được nhiều phiên bản logic cùng truy cập.

Hệ thống phải xem xét **khả năng tương thích giữa những luồng thực thi chồng lấp**, đặc biệt nếu instrumentation làm thay đổi side effects chứ không chỉ thêm telemetry.

### 6.3. Không thể dựa vào thời gian sleep tùy ý

Một demo thiếu đồng bộ thường dùng:

~~~java
Thread.sleep(500);
retransform();
Thread.sleep(500);
~~~

**Đây là trích đoạn không độc lập và không chứng minh thread đã vào method.** Trên máy bận, JIT warmup hoặc GC pause, thread có thể chưa đạt vị trí cần quan sát. Để chứng minh active frame, cần barrier/latch/phaser hoặc một cách đồng bộ có điều kiện xác định được.

Trong demo chính, `ENTERED.await()` và `RELEASE.await()` loại trừ sai lệch quan trọng: main không thể retransform trước khi worker báo đã vào method; worker không thể in `OLD:resumed` trước khi main giải phóng sau retransformation.

## 7. Static state, instance state và class initialization

Trong quá trình retransformation thành công:

- **Lớp không tự chạy lại static initializer (`<clinit>`).** Ví dụ nếu class có `static int counter=10` rồi counter tăng lên 80, retransformation không tự đặt counter về 10.
- **Các instance đã cấp phát không bị tạo mới**, không tự chạy constructor và không bị gán lại field theo bytecode mới.
- **Giá trị static và instance fields hiện có tiếp tục tồn tại**; bytecode mới có thể đọc/ghi các field tương thích đó trong lần gọi method mới.
- **Khác method body không đòi thay class identity.** Object reference tồn tại trước đó vẫn có thể được dùng.
- **Không thêm field mới tùy ý** rồi mong JVM tự đặt giá trị mặc định trong object cũ; schema-change không phải quyền phổ thông của retransform.

Ví dụ khái niệm:

~~~text
Trước:
  service.counter == 7
  frame #1: work() V1 đang chờ

Retransform work() -> V2:
  service.counter vẫn == 7
  frame #1 tiếp tục V1

Sau:
  frame #2: work() V2 có thể thấy counter == 7
~~~

Nếu một framework dùng cache, object state và code version có thể tạm thời lệch nhau về mặt **quy ước nghiệp vụ**. Instrumentation nên có khả năng chịu trạng thái cũ, không giả định mọi object đã được “migration” bởi retransformation.

## 8. Tác động đối với tracing, metrics và profiling

### 8.1. Bật probe ở giữa một request

Giả sử lúc `t0` request A vào `Service.process()`, lúc `t1` agent retransform class để chèn timer, và lúc `t2` request A thoát:

~~~text
t0 request A vào process V1 ---------- đang hoạt động ------------ t2 return
                                 ^
                                 t1 retransform sang V2
                                                             
t3 request B vào process V2 ---- ghi metric/trace mới ----> return
~~~

Nếu timer chỉ có trong **V2**, frame V1 của request A **không tự nhận lời gọi timer được chèn**. Do đó A có thể không xuất hiện trong metric/trace mới dù nó hoàn thành sau `t1`. Request B khởi chạy sau update thường là trường hợp kiểm chứng thích hợp.

### 8.2. Không lấy thời điểm attach làm ranh giới dữ liệu tuyệt đối

Phân biệt những mốc:

1. Agent đã được JVM nạp.
2. Transformer đã đăng ký.
3. Một class cụ thể đã được retransform thành công.
4. Các invocation mới của method đã bắt đầu chạy định nghĩa mới.
5. Các active frames cũ đã thoát hết.
6. Telemetry mới đã được xuất/thu nhận thành công.

Nếu dashboard gắn nhãn “enabled” ngay tại mốc 1 thì không có nghĩa tất cả request sau đó đều được instrument đầy đủ. Nhất là request dài bắt đầu **trước** mốc 3, dữ liệu có thể thiếu phần đầu hoặc toàn bộ method đó.

### 8.3. Tránh nhầm sự kiện cũ với việc probe không hoạt động

Sau khi deploy agent, có thể gặp tình trạng:

- Một số request cũ không ghi metric → **có thể là active frames V1**.
- Request mới có metric → **V2 đã được dùng cho new invokes**.
- Một vài method sâu bên trong request cũ có metric → chúng là **new invokes** được thực hiện từ frame cũ sau update.
- Request hoàn thành nhưng không có span matching → không nhất thiết do exporter hỏng; cần kiểm tra invocation bắt đầu lúc nào.

Khi debug, hãy ghi **timestamp của retransform thành công**, classloader/class identity, số class được cập nhật và một probe identity/version label phù hợp. Có thể dùng counter phân biệt số invocation V1/V2 trong môi trường thử nghiệm. Đừng lấy số completion event làm đại diện tuyệt đối cho số lời gọi đã đi qua version mới.

## 9. Cơ chế JIT và độ trễ thực tế

JVM có thể chạy method bằng interpreter, JIT compiler hoặc đã tối ưu/inlining. Retransformation có thể buộc VM **hủy hiệu lực một số compiled code, deopt hoặc thực hiện safepoint/handshake tùy triển khai** để bảo đảm ngữ nghĩa. Điều này có thể gây gián đoạn hoặc overhead mà demo nhỏ không thể phản ánh.

**Cam kết ở cấp API là ngữ nghĩa method version**, không phải cam kết không có stop-the-world pause, không có deoptimization, hay thời gian `retransformClasses` luôn dưới một ngưỡng cụ thể.

Khi bật instrumentation trên dịch vụ production, cần đo:

- thời gian trả về của `retransformClasses`;
- CPU spike và biến động JIT/deoptimization;
- p95/p99 latency của các request;
- allocation/GC phát sinh do probe mới;
- số class và class loader được instrument;
- số lần transform lỗi, class bị skip và telemetry drops.

Không retransform toàn bộ `getAllLoadedClasses()` nếu chỉ cần một số method. Hãy lọc theo mục tiêu, xác minh `isModifiableClass` và hạn chế số lớp/batch để giảm tác động.

## 10. Retransformation khác gì redefinition và tải lại lớp?

| Cơ chế | Cách hoạt động | Active frame | Lời gọi mới | Object và class identity |
|---|---|---|---|---|
| `Instrumentation.retransformClasses` | Chạy lại pipeline transformer trên class đã nạp | Tiếp tục bytecode version cũ | Dùng method đã retransform nếu thành công | Giữ identity/state |
| `Instrumentation.redefineClasses` | Nhận classfile bytes thay thế trực tiếp | Tiếp tục bytecode version cũ | Dùng method đã redefine nếu thành công | Giữ identity/state |
| Nạp class khác bằng **class loader mới** | Tạo một class identity khác dù tên giống | Frame cũ thuộc class identity cũ | Phụ thuộc loader/reference nào được gọi | **Không phải** cùng class; object cũ không tự chuyển kiểu |
| Khởi động lại JVM | Process mới và class load mới | Frame cũ kết thúc theo vòng đời process | Mọi invocation của process mới | State in-memory thường phải khởi tạo lại |

Theo Java SE 17, cả `retransformClasses` và `redefineClasses` đều quy định active frames tiếp tục original bytecodes và new invokes dùng definition mới. Sự khác nhau chủ yếu là **nguồn bytecode và workflow cập nhật**, không phải cơ chế “đánh tráo stack frame”.

### 10.1. Vì sao không dùng ClassLoader mới thay retransform?

Nếu tạo một `URLClassLoader` mới rồi nạp một lớp cùng tên `demo.HotMethod`, JVM có thể có **hai class identities** khác nhau. Object của class cũ **không tự trở thành instance** của class từ loader mới. Callsite còn giữ tham chiếu tới object/class cũ có thể tiếp tục sử dụng phiên bản cũ, và có thể xảy ra `ClassCastException`/linkage conflicts nếu trộn type từ hai loader.

Retransformation trong demo khác hẳn: chỉ có **một class identity và một object**, nhưng method body được thay đổi cho các invocation mới.

### 10.2. Không tự động hoàn nguyên khi remove transformer

Trong demo:

~~~java
inst.addTransformer(tx, true);
try {
    inst.retransformClasses(target);
} finally {
    inst.removeTransformer(tx);
}
~~~

Việc gỡ `tx` nhằm ngăn callback của transformer đó tham gia các lần biến đổi **sau này**. Nó **không tự gây một lần retransform để đưa V1 trở lại**. Nếu muốn rollback, phải có một bước cập nhật definition khác đã được thiết kế và kiểm thử; đồng thời nhớ **những frame V2 đã bắt đầu trước rollback cũng có thể tiếp tục V2**.

Rollback vì vậy cũng có cửa sổ chồng lấp giữa các method versions. Đừng khẳng định chỉ một thao tác gỡ transformer sẽ khiến tất cả thread trở về hành vi cũ ngay lập tức.

## 11. Các lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Frame cũ vẫn in `OLD` sau retransform | **Hành vi đúng theo API**: frame đã bắt đầu V1 | Kiểm tra invocation mới, không đòi active frame chuyển version |
| Lời gọi mới vẫn chạy V1 | Chưa retransform thành công, transformer không đủ capability, class không đúng, hoặc bytes thay thế không được dùng | Xem manifest, `isRetransformClassesSupported`, `isModifiableClass`, callback filter và output |
| Không thấy `agent:transform` | Transformer chưa đăng ký với `true` hoặc target class không khớp | Đăng ký trước khi gọi `retransformClasses`; kiểm tra `classBeingRedefined` |
| `UnmodifiableClassException` | VM/class đích không cho thay đổi | Bỏ class không modifiable, chọn biện pháp khác |
| `UnsupportedOperationException` hoặc lỗi thay schema | V2 thêm/xóa field/method hoặc đổi hierarchy/signature không được phép | Chỉ biến đổi method body hợp lệ, kiểm tra cấu trúc cả hai phiên bản |
| `ClassFormatError` / `VerifyError` | Class bytes V2 hoặc transformer chain không hợp lệ | Kiểm tra bytecode, stack map, constant pool, class version và verifier |
| Output không đúng thứ tự khi demo dùng `sleep` | Race timing giữa thread | Dùng `CountDownLatch` như ví dụ, không suy từ thời gian sleep |
| Metrics chưa phủ request cũ | Request đã vào method trước instrumentation | Ghi rõ mốc bắt đầu invocation; dựa trên telemetry cũ nếu cần lịch sử |
| Metric đếm gấp đôi sau nhiều lần apply | Transformer chèn probe lặp hoặc nhiều agent cùng instrument | Bảo đảm idempotence, nhận diện probe đã tồn tại, quản lý lifecycle |
| App chậm lúc bật instrumentation | Retransform nhiều class, JIT deopt, probe tốn thời gian | Thu hẹp class, đo p95/p99/CPU/GC, triển khai theo batch |
| Rollback rồi vẫn có V2 | Frame V2 đã bắt đầu hoặc chưa thực hiện update definition để quay lại V1 | Xác nhận workflow rollback và chờ/đo active requests |

### 11.1. Cần kiểm tra cả class loader và tên class

Tên `demo/HotMethod` trong callback chỉ là bước lọc đầu tiên. Trong ứng dụng nhiều class loader, có thể có **nhiều class cùng binary name**. Ví dụ dùng `target == redefining` để tránh sửa nhầm instance `Class<?>` của loader khác.

Cũng cần kiểm tra `Instrumentation.getAllLoadedClasses()`, `isModifiableClass`, module và class loader nếu thực hiện attach vào một JVM lớn. Không retransform một class khác chỉ vì tên trùng.

### 11.2. Transformer exception không phải rollback

Nếu transformer `transform` ném `IllegalClassFormatException` hoặc ngoại lệ callback, JVM còn có quy tắc xử lý lỗi của `ClassFileTransformer`; một ngoại lệ callback **không tự đồng nghĩa ngăn load/retransform**. Nhưng nếu bytes cuối không hợp lệ, `retransformClasses` có thể thất bại khi cài definition.

Vì vậy, khi đánh giá “thành công”, đừng chỉ kiểm tra callback đã được gọi. Cần kiểm tra `retransformClasses` trả về bình thường, và nếu yêu cầu hành vi cụ thể thì **kiểm chứng bằng invocation mới** như demo.

## 12. Checklist vận hành khi bật instrumentation giữa lúc chạy

### Trước thay đổi

- [ ] Định nghĩa **mốc** bắt đầu tính dữ liệu mới: sau khi từng class đã retransform thành công.
- [ ] Biết những request dài hoặc frames cũ có thể tiếp tục bytecode trước thay đổi.
- [ ] Xác định đúng class identity/loader; không chỉ lọc theo tên.
- [ ] Kiểm tra `Can-Retransform-Classes`, `isRetransformClassesSupported` và `isModifiableClass`.
- [ ] Đảm bảo không thay đổi class schema trái giới hạn.
- [ ] Kiểm tra helper class và phụ thuộc do probe thêm được loader đích nhìn thấy.
- [ ] Chuẩn bị thử nghiệm trên JVM/classfile version mục tiêu; test với `-Xverify:all` trong môi trường cô lập.
- [ ] Có phương án khôi phục nếu transform thất bại; tránh cập nhật trên toàn bộ class cùng lúc khi không cần.

### Trong lúc thay đổi

- [ ] Ghi log/metric thời điểm bắt đầu và kết thúc `retransformClasses`.
- [ ] Đo số class thành công/lỗi, không đồng nhất callback với definition installed.
- [ ] Theo dõi latency/CPU/GC/JIT trên traffic thật.
- [ ] Không thực hiện thao tác nặng hoặc blocking I/O trong transformer.
- [ ] Không giữ reference lớp/object quá lâu gây classloader leak.
- [ ] Tránh retransform trùng hoặc nhiều agent ghi đè nhau mà không kiểm soát thứ tự.

### Sau thay đổi

- [ ] Kiểm tra một **invocation mới** chạy version mới.
- [ ] Chấp nhận các active frames từ trước có thể hoàn tất bằng old bytecodes.
- [ ] Đối chiếu telemetry theo thời điểm invocation bắt đầu, không chỉ thời điểm hoàn tất.
- [ ] Không gán thiếu span/metric của request cũ thành bằng chứng agent hỏng.
- [ ] Kiểm tra trạng thái static/instance không bị reset, class identity không đổi.
- [ ] Có kế hoạch rollback riêng; `removeTransformer` không hoàn nguyên những frame đã chạy.
- [ ] Định nghĩa lúc nào dữ liệu đã đủ độ phủ để đánh giá SLA/đo đạc.

## 13. Bài tập tự luyện và câu hỏi kiểm tra

### Bài tập A — dự đoán output

Với demo mục 5, hãy viết ra thứ tự sáu dòng stdout **trước khi chạy**. Vì sao `OLD:resumed` xuất hiện **sau** `main:after-retransform` nhưng vẫn là OLD?

**Đáp án:** Thread worker đã bắt đầu method V1 trước khi retransform. Latch chỉ tạm dừng việc thực thi frame; nó không tạo invocation mới khi được đánh thức.

### Bài tập B — cùng lúc có V1 và V2

Chuyển `service.work()` vào giữa `main:after-retransform` và `RELEASE.countDown()` (điều chỉnh `try/finally` cho đúng). Nếu JVM chấp nhận retransformation, có thể thấy `NEW:invoked` khi worker cũ vẫn bị khóa. Giải thích tại sao hai method versions cùng tồn tại nhưng chỉ có một `HotMethod.class` identity.

### Bài tập C — kiểm tra trạng thái object

Thêm một field `int count` giống nhau ở cả hai bản V1/V2, khởi tạo/gán ở constructor V1 trước update. Bản V2 in `count`. Nếu retransformation thành công, dự đoán nó thấy giá trị cũ hay giá trị mặc định. Hãy giải thích tại sao **retransform không tạo object mới**.

**Lưu ý:** vì trường được thêm vào *source test của cả hai bản trước khi build*, class schema vẫn giống nhau. Không thử thêm một field **chỉ ở V2** rồi kỳ vọng JVM hỗ trợ thay schema.

### Bài tập D — đánh giá tracing

Một span bắt đầu từ request A trước thời điểm retransform, request B bắt đầu sau. Nếu V2 mới thêm probe ở entry `work()`, tại sao A có thể không có entry span mới dù B có? Nếu A gọi một method khác **sau** update, tại sao method được gọi đó vẫn có thể có probe mới?

### Bài tập E — khi rollback

Đã cài V2, sau đó cài lại V1. Hãy nêu ba nhóm có thể cùng tồn tại trong thời gian ngắn: **frame V1 cũ từ trước lần cập nhật**, **frame V2 bắt đầu giữa hai lần cập nhật**, và **invocation mới sau rollback chạy V1**. Vì sao rollback không thể buộc toàn bộ active frames “đổi code ngay”?

### Bài tập F — lỗi do thay schema

Sửa V2 để thêm method mới hoặc đổi descriptor của `work()`. JVM sẽ có quyền từ chối retransformation vì vi phạm ràng buộc schema. Khôi phục signature giống V1 rồi chạy lại; cách làm này giúp tách vấn đề **method version** khỏi vấn đề **type structure**.

### Câu hỏi nhanh

1. **Active frame đang chạy V1 có tự chuyển sang bytecode V2 sau retransform không?** — Không; nó tiếp tục bytecode của phiên bản ban đầu.
2. **Một lời gọi `work()` mới trên chính object cũ có dùng V2 không?** — Có, sau khi V2 đã được cài thành công và không bị thay lần nữa.
3. **`retransformClasses` có tự gọi lại constructor hoặc static initializer không?** — Không, ngoài những gì xảy ra theo ngữ nghĩa khởi tạo JVM thông thường.
4. **`addTransformer(tx, true)` có tự cập nhật các lớp đã nạp không?** — Không; cần chủ động gọi `retransformClasses`.
5. **`Can-Retransform-Classes: true` có tự bảo đảm VM hỗ trợ mọi class không?** — Không; kiểm tra capability và `isModifiableClass`.
6. **Trong cùng một request có thể xuất hiện code V1 và code V2 không?** — Có, nếu một frame cũ gọi một method mới sau khi update.
7. **`removeTransformer` có rollback V2 không?** — Không tự làm việc đó.
8. **Muốn chứng minh version mới có hiệu lực, nên quan sát gì?** — Một invocation bắt đầu sau `retransformClasses` thành công, không chỉ callback.
9. **Nếu retransform ném exception, có được coi V2 đã cài cho một phần tập lớp không?** — Theo Javadoc, không có class trong tập yêu cầu đã được retransform.
10. **Điều cần làm khi bật metric giữa traffic đang chạy?** — Ghi mốc cập nhật, đánh giá riêng request cũ và mới, kiểm thử độ phủ và overhead.

## 14. Tổng kết và tài liệu tham khảo

**Kết luận cốt lõi:** `retransformClasses` thay definition của class để **những invocation mới** chạy method đã biến đổi, nhưng **không viết lại bytecode đang được một active frame thực thi**. Một object có thể được gọi lần đầu bằng V1, lần sau bằng V2; field, static state và class identity của nó vẫn được giữ nguyên. Điều này tạo cửa sổ có nhiều method versions trong quá trình chuyển đổi, cần được tính đến trong instrumentation, tracing, hot fix và rollback.

**Khi kiểm chứng, hãy đồng bộ thí nghiệm bằng latch/barrier, quan sát method đang chạy trước update và tạo invocation mới sau khi update hoàn tất**. Chỉ sự xuất hiện của callback transformer không đủ để chứng minh definition đã cài.

Tài liệu chính thức:

- [Java SE 17 — Instrumentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): hợp đồng `retransformClasses`, active frames, new invokes, giữ instance/static state và hạn chế class change.
- [Java SE 17 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): pipeline transformer, `canRetransform` và xử lý bytes.
- [Java SE 17 — java.lang.instrument package](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): `-javaagent`, `premain`, manifest và JVM initialization.
- [JVMTI — RetransformClasses](https://docs.oracle.com/en/java/javase/17/docs/specs/jvmti.html#RetransformClasses): mô hình native JVMTI tương ứng, method versions và active frames.
- [Java SE 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): đồng bộ xác định thứ tự để kiểm thử.
