# `removeTransformer` và khả năng callback đang chạy vẫn tiếp tục

> **Ngữ cảnh:** Java Advance → Instrumentation → **Chuỗi biến đổi**. Nội dung tập trung vào hợp đồng `Instrumentation.removeTransformer(ClassFileTransformer)`, tình huống tải class đồng thời và cách ngừng transformer mà không làm hỏng callback đang thực thi. Ví dụ Java 17+ dùng startup agent, không phụ thuộc thư viện bytecode.

## 1. `removeTransformer` gỡ đăng ký, không hủy một lời gọi đã bắt đầu

Agent đăng ký transformer qua `Instrumentation.addTransformer(...)`:

~~~java
instrumentation.addTransformer(transformer);
boolean removed = instrumentation.removeTransformer(transformer);
~~~

Theo Java SE API, `removeTransformer(transformer)`:

- **Gỡ một lượt đăng ký** của object transformer được cung cấp khỏi danh sách JVM đang quản lý.
- Trả `true` khi tìm thấy và gỡ được, `false` khi không tìm thấy. Nếu truyền `null`, ném `NullPointerException`.
- Nếu **cùng một object** được đăng ký nhiều lần, gỡ lượt đăng ký khớp **gần nhất**; các lượt khác vẫn có thể tiếp tục nhận callback. Javadoc khuyến cáo tránh đăng ký trùng.
- Khi đã gỡ, các yêu cầu định nghĩa class mới không còn đi qua lượt đăng ký đó. **Tuy nhiên**, do class loading có thể xảy ra trên nhiều thread, một transformer **có thể tiếp tục nhận callback sau khi bị gỡ**, hoặc callback đã bắt đầu có thể tiếp tục chạy.

Điều quan trọng: **`removed == true` chỉ xác nhận gỡ registration thành công; nó không xác nhận các thread đã thoát khỏi `transform(...)`.** Không có bảo đảm `removeTransformer` sẽ chặn, interrupt, cancel hay chờ tất cả invocation trước đó.

### Một cách nhìn về cuộc đua

~~~text
Thread L (định nghĩa class)         Thread M (quản lý agent)
───────────────────────────         ────────────────────────
JVM bắt đầu định nghĩa class A
 └─ chọn transformer T
    └─ T.transform(A) bắt đầu
       └─ đang xử lý...              removeTransformer(T) trả true
       └─ vẫn xử lý tiếp...
       └─ T.transform(A) xong
JVM hoàn tất class A

Sau đó bắt đầu định nghĩa class B
 └─ T không còn registration
    (nếu không có registration trùng/race tồn đọng)
~~~

Đây là **một lịch thực thi hợp lệ**, không phải thứ tự mọi JVM bắt buộc thực hiện. Trong một lịch khác, JVM có thể đã quyết định gọi T trước lúc unregister nhưng thread thực thi chưa đi vào thân Java của `transform`. Khi thread đó tiếp tục, callback **có thể bắt đầu sau cả thời điểm remove trả về**. Chính vì thế Javadoc yêu cầu transformer được viết phòng thủ đối với callback đến trễ.

Một khi callback đã có reference đến các resource của agent, unregister không tự xóa reference đó. Đóng queue, file, logger hoặc connection chung ngay khi `removeTransformer == true` có thể làm callback còn đang chạy gặp lỗi.

## 2. Những điều có thể và không thể kết luận

| Tình huống | Kết luận đúng | Suy diễn sai cần tránh |
|---|---|---|
| `removeTransformer(t) == true` | Đã gỡ **một** lượt đăng ký của `t` | Tất cả callback của t đã dừng |
| `removeTransformer(t) == false` | Không tìm được lượt đăng ký trong thời điểm gọi | T chắc chắn chưa bao giờ được đăng ký |
| Vẫn thấy log callback sau khi remove | Có lời gọi còn hoạt động, đến trễ hoặc lượt đăng ký khác | JVM chắc chắn bỏ qua yêu cầu remove |
| Load class mới sau khi remove mà không còn callback | Registration đã gỡ không xử lý lần load mới trong thử nghiệm ấy | Bytecode của mọi class cũ đã phục hồi |
| Cùng object `t` được đăng ký hai lần rồi gỡ một lần | Vẫn có thể còn một registration của `t` | Gỡ một lần sẽ xóa hết các registration |
| Transformer A đã gỡ nhưng transformer B còn trong chain | B vẫn có thể xử lý lớp mới | removeTransformer xóa toàn bộ chuỗi |

Hãy phân biệt **registration lifecycle** (đang đăng ký hay đã gỡ) với **callback lifecycle** (chưa chạy, đang chạy, đã kết thúc). `removeTransformer` chỉ cung cấp API cho phần thứ nhất.

## 3. Hợp đồng khi có nhiều transformer

Hai overload:

~~~java
instrumentation.addTransformer(t);        // tương đương addTransformer(t, false)
instrumentation.addTransformer(t, false);
instrumentation.addTransformer(t, true); // nếu JVM và agent hỗ trợ retransform
~~~

Transformer được thêm bằng `canRetransform=false` vẫn có thể chạy trên class load/redefinition; nó không được gọi lại khi retransformation nhưng kết quả trước có thể được JVM tái sử dụng khi thích hợp. Transformer có `canRetransform=true` có thể nhận callback trên retransform, nếu JVM hỗ trợ và manifest agent khai capability tương ứng. **Cả hai loại đều gỡ bằng cùng một `removeTransformer(t)`**.

Khi có nhiều transformer, JVM xếp thứ tự xử lý theo nhóm không hỗ trợ/có hỗ trợ retransformation (kể cả native transformer), và theo thứ tự đăng ký trong từng nhóm. Các bước được nối thành chain: mảng byte được một transformer trả về có thể làm input cho transformer kế tiếp. Gỡ một registration không hủy các transformer còn lại; cũng không phải rollback bytes đã được cài vào class.

### Đăng ký trùng cùng instance

Đoạn sau **chỉ là mã minh họa**, biến `instrumentation` và `t` đã có từ một agent bên ngoài:

~~~java
instrumentation.addTransformer(t);
instrumentation.addTransformer(t); // không nên làm như vậy

boolean first = instrumentation.removeTransformer(t);  // true
boolean second = instrumentation.removeTransformer(t); // true
boolean third = instrumentation.removeTransformer(t);  // false
~~~

Lần `first` chỉ gỡ registration gần nhất. Nếu không gọi `second`, vẫn có thể có callback mới dù lệnh remove đầu đã trả `true`. Để quản lý đúng lifecycle, nên lưu **cùng object reference** đã truyền vào `addTransformer`, tránh tự tạo một object mới rồi gọi `removeTransformer(new MyTransformer())`. Nếu có nhiều transformer, mỗi object phải có ownership rõ ràng.

## 4. Ví dụ Java 17+: callback đang chạy vẫn hoàn thành sau remove

Mục tiêu: **điều khiển được thứ tự giữa callback và unregister**, không dựa vào `sleep` ngẫu nhiên.

Thiết kế gồm:

1. Startup agent đăng ký một transformer chỉ log; transformer luôn `return null`, tức **không sửa bytecode**.
2. Ứng dụng cho thread phụ load `FirstTarget`. Trong `transform`, agent phát tín hiệu đã vào callback qua `CountDownLatch ENTERED` rồi chờ ở `RELEASE`.
3. Main thread đợi `ENTERED`, gọi `removeTransformer`, rồi mở `RELEASE`. Callback cũ có thể in tiếp dòng kết thúc.
4. Sau khi thread phụ load xong, main load `SecondTarget`. Class mới vẫn được định nghĩa, nhưng transformer đã bị gỡ không còn log cho class này.

### 4.1 Cấu trúc thư mục

~~~text
remove-transformer-lab/
├── manifest.mf
├── src/
│   └── lab/
│       ├── agent/
│       │   └── GateAgent.java
│       ├── app/
│       │   └── RemoveDemo.java
│       └── targets/
│           ├── FirstTarget.java
│           └── SecondTarget.java
└── out/                         # được tạo khi build
    ├── agent/
    ├── app/
    └── gate-agent.jar
~~~

Dùng JDK 17+ có `java`, `javac` và `jar`. Chạy các lệnh trong thư mục gốc `remove-transformer-lab`; không cần Spring/Gradle/Maven.

### 4.2 Agent: `src/lab/agent/GateAgent.java`

~~~java
package lab.agent;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public final class GateAgent {
    private static final CountDownLatch ENTERED = new CountDownLatch(1);
    private static final CountDownLatch RELEASE = new CountDownLatch(1);
    private static final ClassFileTransformer PROBE = new GateProbe();
    private static Instrumentation instrumentation;

    private GateAgent() {}

    public static void premain(String options, Instrumentation inst) {
        instrumentation = inst;
        inst.addTransformer(PROBE);
        System.out.println("[AGENT] registered");
    }

    public static void awaitFirstCallback() throws InterruptedException {
        if (!ENTERED.await(10, TimeUnit.SECONDS)) {
            throw new IllegalStateException("FirstTarget callback not observed");
        }
    }

    public static boolean remove() {
        return instrumentation.removeTransformer(PROBE);
    }

    public static void releaseFirstCallback() {
        RELEASE.countDown();
    }

    private static final class GateProbe implements ClassFileTransformer {
        @Override
        public byte[] transform(Module module, ClassLoader loader, String className,
                Class<?> classBeingRedefined, ProtectionDomain protectionDomain,
                byte[] classfileBuffer) {

            if ("lab/targets/FirstTarget".equals(className)) {
                System.out.println("[CALLBACK] FirstTarget begin");
                ENTERED.countDown();

                try {
                    if (!RELEASE.await(15, TimeUnit.SECONDS)) {
                        System.out.println("[CALLBACK] safety timeout");
                    }
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }

                System.out.println("[CALLBACK] FirstTarget end");
            } else if ("lab/targets/SecondTarget".equals(className)) {
                System.out.println("[CALLBACK] SecondTarget observed");
            }
            return null;
        }
    }
}
~~~

Giải thích:

- `premain` đăng ký **chính object `PROBE`** trước khi ứng dụng bắt đầu; không dùng retransform, vì vậy không cần manifest `Can-Retransform-Classes`.
- Trong `transform`, so sánh bằng `"literal".equals(className)` tránh NPE nếu className không xác định. JVM dùng internal name có dấu `/`, ví dụ `lab/targets/FirstTarget`.
- Khi class thứ nhất được định nghĩa, callback in `begin`, báo `ENTERED` và chờ `RELEASE`. Trong thời gian chờ, callback **vẫn còn trên call stack**.
- Mốc `SecondTarget observed` được dành riêng để phát hiện nếu một callback cho class thứ hai xảy ra.
- `return null` bảo đảm transformer này không thay bytecode. Latch chặn callback chỉ phục vụ **thí nghiệm**, không dùng trong transformer production.
- Có timeout 15 giây để tránh treo mãi nếu runtime triển khai unregister khác với lịch minh họa. Khi timeout, sẽ in thêm `safety timeout` và output có thể khác.

### 4.3 Hai class mục tiêu

`src/lab/targets/FirstTarget.java`:

~~~java
package lab.targets;

public final class FirstTarget {
    static {
        System.out.println("[TARGET] FirstTarget initialized");
    }
}
~~~

`src/lab/targets/SecondTarget.java`:

~~~java
package lab.targets;

public final class SecondTarget {
    static {
        System.out.println("[TARGET] SecondTarget initialized");
    }
}
~~~

Mốc `[TARGET] ... initialized` do **class initialization**, còn `[CALLBACK]` do JVM gọi transformer trong lúc xử lý định nghĩa class. Đừng nhầm một static initializer chạy với transformer callback.

### 4.4 Ứng dụng: `src/lab/app/RemoveDemo.java`

~~~java
package lab.app;

import lab.agent.GateAgent;
import java.util.concurrent.atomic.AtomicReference;

public final class RemoveDemo {
    public static void main(String[] args) throws Exception {
        AtomicReference<Throwable> loadFailure = new AtomicReference<>();

        Thread loadingThread = new Thread(() -> {
            try {
                Class.forName("lab.targets.FirstTarget");
            } catch (Throwable failure) {
                loadFailure.set(failure);
            }
        }, "load-first-target");

        loadingThread.start();
        GateAgent.awaitFirstCallback();

        try {
            System.out.println("[APP] remove=" + GateAgent.remove());
        } finally {
            GateAgent.releaseFirstCallback();
        }

        loadingThread.join();
        if (loadFailure.get() != null) {
            throw new IllegalStateException("FirstTarget load failed", loadFailure.get());
        }

        Class.forName("lab.targets.SecondTarget");
        System.out.println("[APP] remove again=" + GateAgent.remove());
    }
}
~~~

Ở đây main thread chỉ gọi `remove()` **sau khi** callback đã báo `ENTERED`. Việc release trong `finally` cho phép callback tiếp tục cả khi remove gặp lỗi. `loadingThread.join()` đảm bảo không load class thứ hai cho đến khi class thứ nhất hoàn tất; `AtomicReference<Throwable>` đưa lỗi của thread phụ về main, tránh kết quả thành công giả.

### 4.5 Manifest

`manifest.mf` (có dòng trống kết thúc):

~~~text
Manifest-Version: 1.0
Premain-Class: lab.agent.GateAgent

~~~

Sử dụng `-javaagent` ở startup nên entry point là `premain`; không cần `Agent-Class` hay Attach API. Nếu tên class trong manifest không khớp package, JVM có thể dừng trước khi vào `main`.

### 4.6 Biên dịch và chạy

**macOS/Linux (Bash):**

~~~bash
mkdir -p out/agent out/app
javac --release 17 -d out/agent src/lab/agent/GateAgent.java
javac --release 17 -cp out/agent -d out/app src/lab/targets/FirstTarget.java src/lab/targets/SecondTarget.java src/lab/app/RemoveDemo.java
jar --create --file out/gate-agent.jar --manifest manifest.mf -C out/agent .
java -javaagent:out/gate-agent.jar -cp out/agent:out/app lab.app.RemoveDemo
~~~

**Windows PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force -Path out/agent, out/app | Out-Null
javac --release 17 -d out/agent src/lab/agent/GateAgent.java
javac --release 17 -cp out/agent -d out/app src/lab/targets/FirstTarget.java src/lab/targets/SecondTarget.java src/lab/app/RemoveDemo.java
jar --create --file out/gate-agent.jar --manifest manifest.mf -C out/agent .
java "-javaagent:out/gate-agent.jar" -cp "out/agent;out/app" lab.app.RemoveDemo
~~~

Dấu phân cách classpath là `:` trên macOS/Linux, `;` trên Windows. App đưa `out/agent` vào classpath để gọi trực tiếp các phương thức của `GateAgent`; trên system classloader thông thường, startup agent và app dùng cùng class identity của `GateAgent`, cùng instance `PROBE` và các latch.

Có thể xác nhận JAR:

~~~bash
jar --list --file out/gate-agent.jar
~~~

Bạn phải thấy `META-INF/MANIFEST.MF`, `lab/agent/GateAgent.class` và `lab/agent/GateAgent$GateProbe.class`. Đặt `-javaagent` **trước** tên main class trên dòng lệnh.

### 4.7 Stdout kỳ vọng

Với HotSpot/OpenJDK, trong lịch chạy thông thường khi remove hoàn tất trong lúc callback chờ latch:

~~~text
[AGENT] registered
[CALLBACK] FirstTarget begin
[APP] remove=true
[CALLBACK] FirstTarget end
[TARGET] FirstTarget initialized
[TARGET] SecondTarget initialized
[APP] remove again=false
~~~

Diễn giải:

1. `registered`: một transformer được đăng ký.
2. `FirstTarget begin`: JVM đã vào callback. Latch `ENTERED` đảm bảo thread chính nhìn thấy mốc này trước khi gọi remove.
3. `remove=true`: registration đã gỡ khi callback chưa được release.
4. `FirstTarget end` xuất hiện **sau remove=true**: lời gọi `transform` đang bay không bị tự động hủy.
5. `FirstTarget initialized`: class tiếp tục được định nghĩa và khởi tạo sau khi callback trả `null`.
6. `SecondTarget initialized` nhưng không có dòng `SecondTarget observed`: lần load mới sau unregister không qua transformer bị gỡ.
7. `remove again=false`: không còn registration của instance này.

Đây là **output dự kiến của ví dụ**, không phải lời hứa JVM luôn schedule như vậy. Nếu callback timeout hoặc bị interrupt, log có thể khác; nếu remove đợi callback hoàn thành trên một JVM nhất định, timeout giúp tránh bị kẹt vô hạn. Điểm được đặc tả bảo đảm là bạn **không được xem remove như hàng rào xác nhận mọi callback đã kết thúc**.

### 4.8 Hai biến thể để đối chiếu

**Không gọi remove đầu tiên:** thay biểu thức `GateAgent.remove()` đầu bằng một thông báo `remove=skipped`, vẫn release latch. Khi định nghĩa class thứ hai, transformer vẫn đăng ký và in `[CALLBACK] SecondTarget observed`. Lệnh remove cuối trả `true`.

**Gỡ trước khi load FirstTarget:** gọi `GateAgent.remove()` ở đầu main và **bỏ `awaitFirstCallback()`**, vì không có callback đầu tiên phát latch. Khi load hai class, các mốc `[TARGET]` vẫn xuất hiện nhưng không có mốc `[CALLBACK]`. Hai biến thể chỉ để học; không dùng stdout mục 4.7 để so khớp sau khi đã thay mã.

## 5. Làm thế nào để tắt transformer an toàn hơn?

Một pattern là dùng `AtomicBoolean` để callback đến trễ kiểm tra trạng thái rồi trả `null`:

~~~java
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;
import java.util.concurrent.atomic.AtomicBoolean;

final class ManagedTransformer implements ClassFileTransformer {
    private final AtomicBoolean enabled = new AtomicBoolean(true);

    @Override
    public byte[] transform(Module module, ClassLoader loader, String className,
            Class<?> classBeingRedefined, ProtectionDomain pd, byte[] bytes) {
        if (!enabled.get()) {
            return null;
        }

        // Có thể stop() chạy đồng thời tại đây.
        // Chỉ thao tác trên trạng thái/tài nguyên được quản lý an toàn.
        return null;
    }

    void stop(Instrumentation inst) {
        enabled.set(false);
        inst.removeTransformer(this);
    }
}
~~~

Đây là **class minh họa**, chưa có entry point để chạy độc lập. `AtomicBoolean` giúp công bố trạng thái dừng với visibility theo Java Memory Model, nhưng **không hủy callback đã vượt qua lần kiểm tra `enabled.get()`**. Sau khi callback đọc `true`, `stop` có thể xảy ra và callback vẫn tiếp tục.

Nếu shutdown cần đảm bảo hoàn toàn không còn callback sử dụng resource, agent phải có giao thức điều phối riêng giữa **entry**, **exit** và **cleanup**. Chỉ xem `AtomicInteger inFlight == 0` một lần sau remove cũng có thể thiếu callback **đến trễ** từ một quyết định trước đó của JVM. Thiết kế cần kiểm soát admission và trạng thái in-flight chính xác, hoặc giữ tài nguyên nhẹ tồn tại cho đến lúc JVM kết thúc.

Đặc biệt tránh:

- Giữ lock lâu hoặc thực hiện I/O blocking trong `transform`: callback chạy trên đường nhạy cảm của class loading; một circular dependency có thể gây deadlock.
- Gọi `Class.forName(...)` với chính class đang được transformer xử lý: có thể gây recursive loading hoặc lỗi linkage.
- Đóng logger, queue hoặc executor mà callback cũ còn truy cập chỉ vì `removeTransformer == true`.
- Dùng exception tùy tiện để hủy transform: đặc tả `ClassFileTransformer` vẫn cho phép các transformer khác và quá trình class load tiếp tục khi một transformer ném exception.

## 6. Gỡ đăng ký không tự hoàn tác những biến đổi cũ

Giả sử T đã thay bytecode class A khi A được định nghĩa:

~~~text
class A bytes ban đầu
    |
    v
T.transform(A) trả byte[] mới
    |
    v
JVM định nghĩa A theo kết quả đã instrument
    |
    +-- removeTransformer(T) -> true
    |
    v
A vẫn là class đã được định nghĩa; không tự khôi phục bytes
~~~

`removeTransformer` không phải API `undo instrumentation`. Nếu muốn thay class đang có, cần nghiên cứu `retransformClasses(...)` hoặc `redefineClasses(...)`, khả năng hỗ trợ của JVM/manifest, giới hạn thay đổi class và pipeline hiện tại. **Không được khẳng định retransform sau remove luôn trả về bytes gốc**, vì kết quả phụ thuộc các transformer khác, bytes đầu vào, lịch sử transform và runtime.

Một chi tiết cần nhớ: transformer đã đăng ký với `canRetransform=false` không được gọi lại bằng Java callback trên lượt retransform, nhưng JVM có thể tái áp dụng output cũ theo hợp đồng của pipeline. Vì vậy **không thấy callback log** không đồng nghĩa một class đã được phục hồi.

## 7. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| `removeTransformer(t) == true` nhưng vẫn thấy callback | Callback đã bắt đầu/được chọn trước unregister | Thử với latch, thiết kế callback chịu late calls |
| Remove thành công nhưng class mới vẫn kích hoạt cùng transformer | Có registration trùng, hoặc callback đã được xếp trước | Audit mọi `addTransformer`, kiểm tra identity và thời điểm |
| `removeTransformer(new T()) == false` | Gỡ sai object instance | Lưu original reference từ lần đăng ký |
| Remove lần hai trả `false` | Lần trước đã gỡ registration duy nhất | Coi là trạng thái cleanup bình thường |
| Callback lỗi sau khi shutdown | Resource của agent bị đóng quá sớm | Tách unregister và drain/cleanup |
| Test race có kết quả thất thường | Dựa vào `sleep`/scheduling | Dùng latch + timeout + join |
| Class cũ vẫn mang behavior instrument | Không có rollback tự động | Phân biệt unregister với retransform/redefine |
| Không thấy callback ở `retransformClasses` | Transformer không `canRetransform=true` hoặc không còn đăng ký | Kiểm tra capability và danh sách transformer |
| JVM chậm/treo khi thử blocking callback | Class-loading thread bị chặn | Chỉ dùng blocking có kiểm soát trong lab, tránh trên production |

## 8. Câu hỏi tự kiểm tra

1. **`removeTransformer(t)` trả `true` có nghĩa mọi callback của t đã kết thúc?** Không. Đó chỉ là kết quả gỡ một registration.
2. **Callback có thể bắt đầu sau lúc remove trả về không?** Có, theo đặc tả, vì class loading concurrent.
3. **Một instance đăng ký hai lần, remove một lần có gỡ hết?** Không; gỡ lượt khớp được đăng ký gần nhất.
4. **Gọi remove lần hai trả `false` có phải lỗi JVM?** Không, khi đã không còn registration thì đó là kết quả bình thường.
5. **Thay `Thread.sleep` bằng latch có ích gì?** Latch xác nhận callback đã vào, giúp thiết lập thứ tự sự kiện thay vì đoán theo thời gian.
6. **`AtomicBoolean enabled=false` có làm callback đang xử lý dừng ngay?** Không; invocation có thể đã vượt qua checkpoint.
7. **Gỡ transformer có hoàn tác class đã instrument?** Không; unregister không phải rollback.
8. **`transform(...)` trả `null` có ý nghĩa gì?** Transformer này không thay bytes trong lượt xử lý đó.
9. **Có dùng cùng remove cho transformer `canRetransform=true` và `false`?** Có, cả hai được quản lý bằng `removeTransformer`.
10. **Khi nào được đóng resource chung?** Khi giao thức shutdown của agent bảo đảm an toàn cho mọi in-flight/late callback, không chỉ vì remove trả `true`.

## 9. Checklist đưa vào production

- [ ] Giữ reference đúng instance transformer, tránh đăng ký trùng.
- [ ] Phân biệt trạng thái **registered**, **unregistered**, **in-flight** và **drained**.
- [ ] Callback đến trễ có thể xử lý an toàn hoặc trả `null` khi không còn nhận việc mới.
- [ ] Không xem `removeTransformer == true` như `join()` hoặc cancellation.
- [ ] Không đóng resource dùng chung khi callback có thể chưa kết thúc.
- [ ] Tránh block, giữ lock nặng, nạp thêm class hoặc I/O phức tạp trong transformer production.
- [ ] Không nhầm unregister với rollback bytecode.
- [ ] Kiểm thử callback đang chạy, class load sau remove và cleanup lặp.

## Tài liệu chuẩn

- [Java SE 21 — Instrumentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `addTransformer`, `removeTransformer`, giá trị trả về, removal gần nhất, callback đồng thời và `retransformClasses`.
- [Java SE 17 — Instrumentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): hợp đồng tương ứng trên Java 17.
- [Java SE 21 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): quy tắc callback, chaining, return `null`, input classfileBuffer và retransform.
- [Java SE 21 — CountDownLatch](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CountDownLatch.html): đồng bộ thread trong thí nghiệm.
