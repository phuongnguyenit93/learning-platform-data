# Theo dõi lớp ẩn trong thread dump và stack trace phù hợp (Java 15+)

## 1. Bối cảnh: hidden class có thể tồn tại dù stack trace thông thường không hiện nó

**Hidden class (lớp ẩn)** được chuẩn hóa trong **Java 15** qua **JEP 371 — Hidden Classes**. Nó phục vụ các framework hoặc runtime cần định nghĩa lớp động làm **chi tiết triển khai**, ví dụ cơ chế sinh mã khi thực thi. Java cung cấp API chính thức `MethodHandles.Lookup.defineHiddenClass(byte[], boolean, ClassOption...)` để định nghĩa lớp từ bytecode, và `Class.isHidden()` để kiểm tra.

Trong khắc phục lỗi, ta có thể gặp một tình huống tưởng như mâu thuẫn:

- Framework thực sự chạy mã trong một **hidden class**.
- Một exception có `Throwable.getStackTrace()` nhưng không hiện frame của hidden class.
- `StackWalker` mặc định có thể bỏ các **hidden frames**.
- `StackWalker` với `SHOW_HIDDEN_FRAMES` có thể tìm lại frame tương ứng **trên chính thread đang chạy**.
- Một thread dump hoặc `ThreadMXBean` có thể hiển thị cấu trúc khác; **không nên giả định mọi API tạo ra cùng một stack trace**.

Bài này thuộc nhóm **Chẩn đoán lỗi** của module **Java 15**. Trọng tâm là **chọn đúng nguồn quan sát** để điều tra mã lớp ẩn, phân biệt hidden class với hidden frame, hiểu cách đọc tên class động, và biết giới hạn của thread dump, stack trace, `StackWalker`, JFR và `jcmd`. Mã thực hành dùng **Java 17+** và API hiện hành, không dựa vào `sun.misc.Unsafe.defineAnonymousClass` hoặc các API nội bộ/legacy.

> **Điểm quan trọng:** *Hidden class* là một đặc tính của **đối tượng `Class<?>`**; *hidden frame* là một **khung gọi trên stack** được công cụ stack walking mặc định lọc theo quy tắc của JVM. Hai khái niệm liên quan nhưng **không được đánh đồng**.

## 2. Hidden class là gì và có thể nhận diện ra sao?

### 2.1. Cách tạo và nhận diện theo API hiện hành

Một `MethodHandles.Lookup` có đủ quyền có thể định nghĩa hidden class từ một mảng byte chứa class file hợp lệ:

~~~java
MethodHandles.Lookup hiddenLookup =
        MethodHandles.lookup().defineHiddenClass(classBytes, true);

Class<?> hiddenClass = hiddenLookup.lookupClass();
boolean hidden = hiddenClass.isHidden();
String dynamicName = hiddenClass.getName();
~~~

Đây là **đoạn minh họa**, trong đó `classBytes` là bytecode hợp lệ, cùng runtime package với lookup class; `defineHiddenClass` có yêu cầu quyền truy cập của `Lookup` và có thể ném lỗi nếu bytes/điều kiện access không hợp lệ. Mục 7 có chương trình **hoàn chỉnh** lấy bytes từ một class được biên dịch bằng `javac`, không cần thư viện sinh bytecode ngoài.

Các tính chất chính:

| Thuộc tính | Hidden class |
| --- | --- |
| `Class.isHidden()` | Trả `true` với lớp được định nghĩa theo cơ chế hidden class. |
| Tên `Class.getName()` | Có dạng nội bộ với một phần hậu tố được phân tách bằng **`/`**, ví dụ `pkg.Generated/0x...` trên HotSpot; **không phải binary name** hợp lệ theo Java Language Specification. |
| `Class.forName(dynamicName)` | **Không dùng để tìm lại hidden class**. Hidden class không được khám phá bằng cách lookup theo binary name. |
| `ClassLoader.loadClass(dynamicName)` | Cũng không có hợp đồng tìm lại hidden class bằng tên động đó. |
| `Lookup.lookupClass()` | Có thể trả về `Class<?>` của hidden class ngay sau khi `defineHiddenClass`. |
| `MethodHandle` | Có thể giữ đường gọi trực tiếp đến phương thức của hidden class đã được định nghĩa. |
| `ClassOption.NESTMATE` | Cho phép hidden class trở thành nestmate trong bối cảnh phù hợp; quyền private của nest cần tuân thủ access checks. |
| `ClassOption.STRONG` | Gắn vòng đời lớp ẩn mạnh hơn với class loader; mặc định hidden class có thể unload khi không còn references phù hợp. |

**Không nên coi tên `.../0x...` là tên ổn định để triển khai quy tắc nghiệp vụ.** Hậu tố định danh thay đổi giữa lượt chạy và giữa các lần định nghĩa lớp. Khi cần log danh tính của code được sinh, ghi thêm **framework/job ID, handler ID, source mapping, bytecode fingerprint hoặc version code generator** ở tầng ứng dụng, không dựa vào việc hậu tố mang giá trị cố định.

### 2.2. Hidden class không nhất thiết có file .java tương ứng

Lớp ẩn thường được framework sinh bằng bytecode. Frame trong stack trace có thể thiếu `SourceFile`, `LineNumberTable`, hoặc có tên file gốc của một template dùng để tạo lớp. Vì vậy:

- `StackTraceElement.getFileName()` có thể trả `null`.
- `getLineNumber()` có thể trả giá trị âm (không có thông tin dòng).
- Tên phương thức có thể là mã sinh, không ánh xạ trực tiếp tới Java source của ứng dụng.
- Một framework tốt nên bảo tồn thông tin **đầu vào/biểu thức/quy tắc sinh code** để chẩn đoán.

Đừng diễn giải `Unknown Source` thành “JVM không tạo frame”; nó thường là **thiếu metadata nguồn**. Ngược lại, việc có tên file và line number trong frame cũng không chứng minh đây là lớp Java bình thường, vì bytecode lớp ẩn vẫn có thể mang debug metadata.

### 2.3. Nhầm lẫn với anonymous/local classes và lambda

- `new Object() {}` là một **anonymous class theo ngôn ngữ Java**; việc tên chứa `$1` không tự chứng minh `isHidden()==true`.
- `static class Inner` là **nested class**, không mặc nhiên là hidden class.
- Một lambda có thể được hiện thực bằng kỹ thuật sinh lớp ẩn ở một JDK; **chi tiết triển khai của LambdaMetafactory có thể đổi theo runtime**. Không dựa vào chuỗi tên `$$Lambda` hay một suffix cụ thể để kết luận type chính xác.
- Hãy kiểm tra bằng **`Class.isHidden()`** khi thực sự có `Class<?>`, thay vì đoán từ chuỗi log.

## 3. Phân biệt bốn nguồn stack trace phổ biến

| Nguồn | Nó quan sát gì? | Có thể thấy hidden class/frame không? | Hạn chế quan trọng |
| --- | --- | --- | --- |
| `Throwable.getStackTrace()` / `printStackTrace()` | Snapshot khi Throwable được tạo/stack trace được điền, và định dạng exception chain | Có thể **lọc một số hidden frames**; trên HotSpot JDK 24 kiểm thử, frame hidden class không hiện trong `new Exception().getStackTrace()` | Không phải snapshot của mọi thread; có thể bị wrap, cắt, thay đổi bằng `setStackTrace` hoặc trình bày khác bởi logger. |
| `Thread.currentThread().getStackTrace()` và `otherThread.getStackTrace()` | Stack snapshot theo `Thread` | Kết quả cụ thể phụ thuộc JVM; bản thử JDK 24 đã **không hiện** frame hidden class với API này | Lấy ở thời điểm gọi, có race và có thể khác stack lúc exception xảy ra. |
| `StackWalker.getInstance(...)` | Đi qua stack **của thread đang gọi** | Mặc định **lọc hidden frames**; dùng `SHOW_HIDDEN_FRAMES` để hiển thị đầy đủ các hidden frames theo JVM | **Không walk từ thread A sang thread B** bằng StackWalker của thread A. |
| `ThreadMXBean.getThreadInfo(...)` / `jcmd Thread.print` | Thread diagnostic snapshot, thường có trạng thái, stack và thông tin locks | Có thể có những frame mà các API khác lọc; bản JDK 24 kiểm thử cho thấy `ThreadMXBean` có frame hidden class | Phụ thuộc công cụ/runtime, thời điểm lấy mẫu và kiểu thread; `ThreadMXBean` chỉ quản lý platform threads trên Java hiện đại. |

**Đừng viết một parser giả định `Throwable`, `Thread.getStackTrace`, `ThreadMXBean` và `jcmd` luôn chứa cùng số frame/tên frame.** Chúng phục vụ mục đích khác nhau và có thể áp dụng các quy tắc lọc/định dạng khác nhau.

### 3.1. Throwable không nhất thiết giữ toàn bộ đường gọi

~~~java
try {
    executeFrameworkCode();
} catch (Throwable failure) {
    failure.printStackTrace();
}
~~~

Đây là **đoạn minh họa** với `executeFrameworkCode()` do ứng dụng cung cấp. `Throwable` thường ghi stack tại thời điểm được tạo hoặc khi `fillInStackTrace`; nó **không ghi lịch sử mọi thread**. Nếu lỗi đi qua `MethodHandle`, proxy, reflection hay generated class, các frame triển khai có thể bị ẩn theo quy tắc runtime. Nếu framework wrap exception, còn cần xem **`getCause()`**, `getSuppressed()` và exception gốc.

Dòng `... N more` trong `Throwable.printStackTrace()` thường là cách định dạng **bớt các frame chung** của exception cause với phần cha, không tự chứng minh có hidden class. Dòng log bị rút gọn theo cấu hình logger hoặc stack trace depth limit cũng là lý do riêng khác với cơ chế hidden frames.

Không giả định cứ thêm `SHOW_HIDDEN_FRAMES` cho một `StackWalker` mới sẽ **sửa ngược** stack trace đã được `Throwable` chụp; đó là hai API độc lập.

### 3.2. StackWalker: lựa chọn đúng khi cần soi đường gọi hiện tại

~~~java
StackWalker walker = StackWalker.getInstance(
        Set.of(StackWalker.Option.RETAIN_CLASS_REFERENCE,
               StackWalker.Option.SHOW_HIDDEN_FRAMES));

boolean hasHiddenClass = walker.walk(frames ->
        frames.anyMatch(frame -> frame.getDeclaringClass().isHidden()));
~~~

Đây là đoạn minh họa, cần import `java.lang.StackWalker` và `java.util.Set`; chạy **ngay trong thread cần chẩn đoán**.

- `SHOW_HIDDEN_FRAMES`: yêu cầu StackWalker hiển thị các hidden frames, bao gồm reflection frames và các frame triển khai khác theo runtime.
- `RETAIN_CLASS_REFERENCE`: cho phép gọi `StackFrame.getDeclaringClass()`; nếu không có tùy chọn này, API có thể ném `UnsupportedOperationException` khi truy cập `getDeclaringClass()`.
- `StackFrame.getClassName()` và `getMethodName()` cho biết thông tin mô tả; đối với lớp ẩn, **đừng giả định chuỗi class name là binary name có thể nạp bằng Class.forName**.
- `StackWalker.getInstance()` mặc định bỏ qua hidden frames.
- `StackWalker.getCallerClass()` có quy tắc lọc đặc biệt và **vẫn bỏ reflection/MethodHandle/hidden frames**, ngay cả nếu walker được cấp `SHOW_HIDDEN_FRAMES`; không dùng nó để “lấy hidden caller” một cách máy móc.

**Quan trọng:** luồng `Stream<StackFrame>` chỉ hợp lệ bên trong callback `walk(...)`; nó sẽ bị đóng khi callback kết thúc. Không trả stream ra ngoài rồi dùng lại. Nếu cần lưu thông tin chẩn đoán, **materialize** kết quả thành một list/record trong callback. Với hệ thống latency-sensitive, tránh log nguyên stack liên tục trong hot path.

## 4. Thread dump và StackWalker không thay thế cho nhau

### 4.1. Khi nào nên lấy thread dump?

Thread dump hợp lý để chẩn đoán **thread bị treo, deadlock, lock contention, blocking I/O, thread starvation hoặc CPU cao**. Nó cho một **ảnh chụp tại thời điểm quan sát**. Nếu lỗi xảy ra nhanh rồi hết, dump sau khi lỗi qua đi có thể không còn frame của đoạn mã gây lỗi.

Một quy trình chẩn đoán JVM process Java thông thường:

~~~bash
jcmd -l
jcmd <PID> VM.command_line
jcmd <PID> Thread.print -l
~~~

`<PID>` là **PID thật** của tiến trình Java cần điều tra; đây là cú pháp placeholder trong bài hướng dẫn, không phải giá trị đưa nguyên vào shell. `jcmd -l` giúp liệt kê JVM process; `Thread.print -l` yêu cầu thread dump và thông tin locks của `java.util.concurrent` khi runtime hỗ trợ. Cần chạy với user/quyền phù hợp, trên máy hoặc môi trường có khả năng attach đến JVM đích.

Nếu dùng **JDK 21+** có `Thread.dump_to_file`, có thể lấy snapshot thích hợp cho ứng dụng dùng virtual threads:

~~~bash
jcmd <PID> Thread.dump_to_file -format=json /tmp/threads-<PID>.json
~~~

Trên Linux, hãy thay `<PID>` ở cả hai vị trí bằng PID thật, và đảm bảo đường dẫn file được phép ghi; đường dẫn/option cụ thể có thể khác giữa hệ điều hành, phiên bản JDK và công cụ triển khai. Tài liệu `jcmd` của JDK 24/25 dùng option `-format=json`. Với virtual threads (Java 21+), `Thread.dump_to_file` được thiết kế để cung cấp góc nhìn bao gồm virtual threads; **`ThreadMXBean` không bao gồm virtual thread IDs**. Không dùng kết quả `ThreadMXBean.dumpAllThreads` để khẳng định không có vấn đề ở virtual threads.

**Lưu ý:** `jcmd Thread.print` và `Thread.dump_to_file` có mục đích/cách lấy snapshot khác nhau; có thể cung cấp lượng lock/thread information khác nhau theo JDK. Đừng bắt một trong hai có đúng “N khung của lớp ẩn” rồi coi công cụ khác sai.

### 4.2. Chọn đúng thời điểm và đọc tên class động

Nếu dump có frame tên kiểu:

~~~text
at example.GeneratedHandler/0x0000000800123400.execute(GeneratedHandler.java:42)
~~~

Đây là **ví dụ định dạng minh họa**, không phải tên một hidden class cố định. Phần `/0x...` có thể là hậu tố của lớp động. Không xem `/` ở **tên hidden class** như ký tự phân cách module/class loader một cách đơn giản: `StackTraceElement.toString()` có thể thêm cả **module name / class loader name** theo định dạng riêng.

Cách chắc chắn hơn khi có quyền sửa/quan sát code framework là ghi:

- `classRef.isHidden()`;
- `classRef.getName()` (chỉ phục vụ log ở đúng lượt JVM, không làm cache key lâu dài);
- handler ID, operation name, framework-generated source mapping, **template/source version**;
- `thread.getName()` và **thread ID**, request/job correlation ID;
- stack frame method name và source line (nếu metadata tồn tại);
- module, class loader, phiên bản JDK và trace ID khi cần.

Nếu chỉ có một chuỗi frame từ remote dump, **không thể gọi `Class.isHidden()`** vì chưa có `Class<?>` tương ứng. Regex theo hậu tố tên có thể hỗ trợ điều tra **một JDK cụ thể**, nhưng không phải thay thế cho API kiểm tra trực tiếp.

### 4.3. ThreadMXBean: lấy stack của platform thread khác

~~~java
ThreadMXBean bean = ManagementFactory.getThreadMXBean();
ThreadInfo info = bean.getThreadInfo(platformThread.getId(), 100);
if (info != null) {
    for (StackTraceElement f : info.getStackTrace()) {
        System.out.println(f.getClassName() + "." + f.getMethodName());
    }
}
~~~

Đây là **đoạn minh họa**; cần import `java.lang.management.ManagementFactory`, `ThreadMXBean`, `ThreadInfo`, và có biến `platformThread` đã được tạo/đang sống. `getThreadInfo(id, 100)` giới hạn tối đa **100 stack frames**. `info==null` có thể nghĩa là thread đã kết thúc/không tồn tại hoặc đó là virtual thread trên JDK hiện đại.

Không lấy snapshot một lần để kết luận thread không bao giờ vào hidden class. Cần lấy đúng thời điểm khi work đang chạy, hoặc thêm **in-process diagnostics**/JFR events để theo dõi trạng thái có diễn biến nhanh.

## 5. Thực nghiệm quan trọng: API có thể khác nhau trên cùng JDK

Trong một lượt kiểm thử với **JDK 24**, một lớp động được định nghĩa bằng `Lookup.defineHiddenClass(..., NESTMATE)` và một thread đứng chờ trong phương thức của lớp đó. Kết quả quan sát:

| Cách lấy stack | Có frame hidden class ở lần thử? |
| --- | --- |
| `StackWalker` mặc định trong method của hidden class | **Không** |
| `StackWalker` với `SHOW_HIDDEN_FRAMES` và `RETAIN_CLASS_REFERENCE` | **Có** |
| `new Exception().getStackTrace()` tạo trong hidden method | **Không** |
| `Thread.currentThread().getStackTrace()` trong hidden method | **Không** |
| `otherThread.getStackTrace()` khi hidden method đang chờ | **Không** |
| `ThreadMXBean.getThreadInfo(workerId, 100).getStackTrace()` | **Có** |

**Các dòng “Có/Không” trong bảng là dữ liệu đã đo trên HotSpot JDK 24**, không phải một hợp đồng bắt buộc cho tất cả JDK/vendor, công cụ dump hoặc cách tối ưu JIT. **Không nên viết assertion cố định trên số frame/tên suffix trong production**. Điều cần giữ là: chọn API phù hợp với mục đích quan sát, xác nhận version/runtime và diễn giải sự vắng mặt của frame một cách thận trọng.

Một số hidden frames có thể là reflection/MethodHandle implementation frames **ngay cả khi class khai báo frame không phải hidden class**. Ngược lại, một hidden class có thể đang được tham chiếu nhưng không có frame đang chạy tại thời điểm dump. **Không tìm thấy tên `/0x...` trong một thread dump không chứng minh hidden class không tồn tại**.

## 6. Bài thực hành có thể chạy độc lập: dựng hidden class, kiểm tra StackWalker và ThreadMXBean

Ta biên dịch một file Java chứa cả:

- **`HiddenTraceDiagnostics`:** lớp thường chịu trách nhiệm đọc bytecode, tạo hidden class, khởi chạy worker và lấy snapshot thread.
- **`GeneratedBody`:** nested class đóng vai trò **template bytecode**; trình biên dịch tạo file `HiddenTraceDiagnostics$GeneratedBody.class`. Chương trình đọc bytes từ classpath, rồi `defineHiddenClass` để JVM tạo **một lớp ẩn khác** dựa trên bytes đó.

Dùng `ClassOption.NESTMATE` để lớp ẩn có thể truy cập những thành phần private của outer class theo quan hệ nest. Khi worker chạy hidden method, nó thử hai `StackWalker`: mặc định và mở rộng. Sau khi worker báo đã vào method, main dùng `Thread.getStackTrace()` và `ThreadMXBean` lấy snapshot cùng worker đang đợi trên latch. Có `finally` để giải phóng worker kể cả khi assertion thất bại.

### 6.1. Mã hoàn chỉnh: HiddenTraceDiagnostics.java

~~~java
import java.io.InputStream;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;
import java.util.Arrays;
import java.util.Set;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class HiddenTraceDiagnostics {
    private static final CountDownLatch ENTERED = new CountDownLatch(1);
    private static final CountDownLatch RELEASE = new CountDownLatch(1);
    private static final AtomicReference<Throwable> FAILURE = new AtomicReference<>();
    private static volatile boolean defaultShowsHidden;
    private static volatile boolean fullShowsHidden;
    private static volatile boolean throwableShowsHidden;
    private static volatile boolean currentThreadShowsHidden;
    private static int passed;

    private static void check(String label, boolean ok) {
        if (!ok) throw new AssertionError(label);
        passed++;
        System.out.println(label + "=PASS");
    }

    public static class GeneratedBody {
        public static void execute() throws InterruptedException {
            StackWalker ordinary = StackWalker.getInstance(
                    Set.of(StackWalker.Option.RETAIN_CLASS_REFERENCE));
            StackWalker expanded = StackWalker.getInstance(
                    Set.of(StackWalker.Option.RETAIN_CLASS_REFERENCE,
                           StackWalker.Option.SHOW_HIDDEN_FRAMES));
            defaultShowsHidden = ordinary.walk(frames ->
                    frames.anyMatch(f -> f.getDeclaringClass().isHidden()));
            fullShowsHidden = expanded.walk(frames ->
                    frames.anyMatch(f -> f.getDeclaringClass().isHidden()));
            throwableShowsHidden = Arrays.stream(new Exception("sample").getStackTrace())
                    .anyMatch(f -> f.getClassName().contains("/0x"));
            currentThreadShowsHidden = Arrays.stream(Thread.currentThread().getStackTrace())
                    .anyMatch(f -> f.getClassName().contains("/0x"));
            ENTERED.countDown();
            RELEASE.await(5, TimeUnit.SECONDS);
        }
    }

    public static void main(String[] args) throws Throwable {
        byte[] templateBytes;
        try (InputStream input = HiddenTraceDiagnostics.class
                .getResourceAsStream("/HiddenTraceDiagnostics$GeneratedBody.class")) {
            if (input == null) throw new IllegalStateException("Missing class resource");
            templateBytes = input.readAllBytes();
        }

        MethodHandles.Lookup hiddenLookup = MethodHandles.lookup().defineHiddenClass(
                templateBytes, true, MethodHandles.Lookup.ClassOption.NESTMATE);
        Class<?> hiddenClass = hiddenLookup.lookupClass();

        check("classIsHidden", hiddenClass.isHidden());
        check("nameHasSlashSuffix", hiddenClass.getName().contains("/"));
        check("hiddenIsNestmate", hiddenClass.getNestHost() == HiddenTraceDiagnostics.class);

        boolean classForNameRejected = false;
        try {
            Class.forName(hiddenClass.getName());
        } catch (ClassNotFoundException expected) {
            classForNameRejected = true;
        }
        check("classForNameRejected", classForNameRejected);

        MethodHandle handler = hiddenLookup.findStatic(
                hiddenClass, "execute", MethodType.methodType(void.class));
        Thread worker = new Thread(() -> {
            try {
                handler.invokeExact();
            } catch (Throwable failure) {
                FAILURE.set(failure);
            }
        }, "hidden-worker");

        try {
            worker.start();
            check("workerEnteredHiddenMethod", ENTERED.await(5, TimeUnit.SECONDS));
            check("ordinaryWalkerFiltersHidden", !defaultShowsHidden);
            check("expandedWalkerSeesHidden", fullShowsHidden);

            boolean remoteThreadShowsHidden = Arrays.stream(worker.getStackTrace())
                    .anyMatch(f -> f.getClassName().contains("/0x"));
            ThreadMXBean bean = ManagementFactory.getThreadMXBean();
            ThreadInfo info = bean.getThreadInfo(worker.getId(), 100);
            boolean mxBeanShowsHidden = info != null
                    && Arrays.stream(info.getStackTrace())
                             .anyMatch(f -> f.getClassName().contains("/0x"));

            System.out.println("OBS_THROWABLE_HIDDEN=" + throwableShowsHidden);
            System.out.println("OBS_CURRENT_THREAD_HIDDEN=" + currentThreadShowsHidden);
            System.out.println("OBS_REMOTE_THREAD_HIDDEN=" + remoteThreadShowsHidden);
            System.out.println("OBS_THREAD_MXBEAN_HIDDEN=" + mxBeanShowsHidden);
        } finally {
            RELEASE.countDown();
            worker.join(2000);
        }

        check("workerTerminated", !worker.isAlive());
        check("workerFailureAbsent", FAILURE.get() == null);
        System.out.println("TOTAL_PASS=" + passed);
    }
}
~~~

### 6.2. Biên dịch và chạy

Lưu file bằng UTF-8 tại một thư mục riêng:

~~~bash
javac --release 17 -encoding UTF-8 -g HiddenTraceDiagnostics.java
java HiddenTraceDiagnostics
~~~

**Không dùng source-file launcher `java HiddenTraceDiagnostics.java` để thay thế quy trình này:** ví dụ cần file **`HiddenTraceDiagnostics$GeneratedBody.class`** đã được tạo bởi `javac` và tìm thấy trên classpath. Lệnh ở trên chạy đúng khi đứng trong thư mục chứa cả hai file `.class` và file nguồn, hoặc đặt `-cp` về thư mục biên dịch.

**Stdout đã kiểm tra trên HotSpot JDK 24**, với tổng **9 phép kiểm tra bắt buộc** và bốn kết quả quan sát:

~~~text
classIsHidden=PASS
nameHasSlashSuffix=PASS
hiddenIsNestmate=PASS
classForNameRejected=PASS
workerEnteredHiddenMethod=PASS
ordinaryWalkerFiltersHidden=PASS
expandedWalkerSeesHidden=PASS
OBS_THROWABLE_HIDDEN=false
OBS_CURRENT_THREAD_HIDDEN=false
OBS_REMOTE_THREAD_HIDDEN=false
OBS_THREAD_MXBEAN_HIDDEN=true
workerTerminated=PASS
workerFailureAbsent=PASS
TOTAL_PASS=9
~~~

**Các dòng `OBS_*` là kết quả quan sát trên JDK 24**, không phải assertion bắt buộc cho mọi runtime. Chương trình không cố định hậu tố tên lớp ẩn, line number, số frame hay trạng thái thread cụ thể ngoài các điều kiện kiểm tra thiết yếu.

### 6.3. Đọc từng phép kiểm tra

| Kết quả | Ý nghĩa |
| --- | --- |
| `classIsHidden=PASS` | `Class.isHidden()` xác nhận lớp được định nghĩa là hidden class thật. |
| `nameHasSlashSuffix=PASS` | Tên hidden class chứa ký tự `/` theo cơ chế tên không-binary. |
| `hiddenIsNestmate=PASS` | `ClassOption.NESTMATE` tạo quan hệ nestmate trong bài thực nghiệm. |
| `classForNameRejected=PASS` | Không tra cứu được hidden class bằng `Class.forName(dynamicName)`. |
| `workerEnteredHiddenMethod=PASS` | Worker đã thực thi phương thức từ hidden class, tránh “lấy snapshot quá sớm”. |
| `ordinaryWalkerFiltersHidden=PASS` | `StackWalker` không có `SHOW_HIDDEN_FRAMES` không phát hiện hidden class frame ở lượt thử. |
| `expandedWalkerSeesHidden=PASS` | Bật `SHOW_HIDDEN_FRAMES` + `RETAIN_CLASS_REFERENCE` cho phép nhận diện frame có `getDeclaringClass().isHidden()==true`. |
| `OBS_THROWABLE_HIDDEN=false` | `Throwable.getStackTrace()` trong hidden method không báo khung lớp ẩn trong lượt thử. |
| `OBS_CURRENT_THREAD_HIDDEN=false` | Thread stack trace mặc định trong hidden method không báo khung lớp ẩn ở lượt thử. |
| `OBS_REMOTE_THREAD_HIDDEN=false` | `worker.getStackTrace()` từ main không báo khung lớp ẩn trong lượt thử. |
| `OBS_THREAD_MXBEAN_HIDDEN=true` | `ThreadMXBean.getThreadInfo` cho thấy khung tên lớp ẩn trong lượt thử. |
| `workerTerminated=PASS` | Worker rời latch và kết thúc sau cleanup. |
| `workerFailureAbsent=PASS` | Không có exception bất ngờ trong hidden method. |

**Tại sao code chỉ tìm `"/0x"` trong bốn kết quả OBS?** Đây là một **dấu hiệu định dạng của HotSpot JDK được thử**, dùng cho việc quan sát, không phải API xác định mọi hidden class. Những assertion thực sự về lớp ẩn dựa trên `Class.isHidden()` và `StackWalker.StackFrame.getDeclaringClass().isHidden()`. Ứng dụng production không nên viết chính sách bảo mật hoặc khôi phục lớp bằng cách phân tích suffix này.

## 7. Quy trình chẩn đoán lớp ẩn ở môi trường thực tế

### Bước 1: xác minh phiên bản và nguồn mã sinh

Ghi lại JDK vendor/build, framework/agent version, source/mapping version, module/class loader, và cách tạo mã động (MethodHandle, proxy, bytecode generation). Nếu đây là một framework thay vì ứng dụng tự sinh mã, kiểm tra tài liệu chẩn đoán của framework về cách bật log/mapping của generated code.

**Không dùng các API nội bộ đã lỗi thời để định nghĩa hidden classes:** dùng `MethodHandles.Lookup.defineHiddenClass` và `Class.isHidden` khi cần can thiệp vào code Java hiện đại.

### Bước 2: xác định loại sự cố

- **Exception tại thời điểm thực thi:** ưu tiên Throwable, cause/suppressed, request trace và thông tin generated-code mapping; thêm in-process `StackWalker` tại boundary quan trọng nếu cần.
- **Thread bị treo/lock:** lấy **nhiều thread dumps theo thời gian**, không chỉ một snapshot; xem `WAITING/BLOCKED/RUNNABLE`, stack, monitors, thread name/ID, CPU.
- **Sự kiện ngắn/tần suất cao:** xem JFR/profiling và application instrumentation vì thread dump có thể luôn bỏ lỡ thời điểm có frame.
- **Vấn đề class loading/metaspace:** xem class load/unload logs, JFR class events và mapping của code generator; một thread dump không chứng minh toàn bộ lớp còn sống hoặc đã unload.

### Bước 3: nếu có quyền sửa code, đặt StackWalker ở điểm thích hợp

Bật `SHOW_HIDDEN_FRAMES` và `RETAIN_CLASS_REFERENCE` **trong chính đường gọi cần chẩn đoán**, lấy danh sách frame giới hạn độ sâu, ghi method/source/line và `isHidden`. Đừng dùng StackWalker ở thread A để cố xem call stack của thread B; hãy dùng `ThreadMXBean`/thread dump/JFR cho nhu cầu quan sát thread khác.

Một đoạn minh họa lưu snapshot gọn:

~~~java
StackWalker detailed = StackWalker.getInstance(Set.of(
        StackWalker.Option.SHOW_HIDDEN_FRAMES,
        StackWalker.Option.RETAIN_CLASS_REFERENCE));

List<String> frames = detailed.walk(stream ->
        stream.limit(30)
              .map(f -> f.getDeclaringClass().isHidden()
                      + " " + f.getClassName() + "#" + f.getMethodName()
                      + ":" + f.getLineNumber())
              .toList());
~~~

Đây là đoạn **không độc lập**, cần import `StackWalker`, `Set` và `List`. `stream.limit(30)` chỉ quan sát 30 frame đầu, tránh ghi log toàn bộ stack vô hạn trong hot path. Khi phân tích mismatch, thông tin **`true/false` từ `isHidden()`** đáng tin hơn đoán hidden class bằng suffix.

### Bước 4: nếu không sửa được code, lấy thread dump và correlate

Dùng `jcmd <PID> Thread.print -l` ở đúng JVM, lấy ít nhất vài snapshot khi tình trạng còn xảy ra. Với Java 21+ và virtual threads, cân nhắc thêm `Thread.dump_to_file`. So sánh theo **thread name/ID, state, blocking call và request ID**, không chỉ tìm một tên class có hậu tố `/0x`.

`ThreadMXBean.getThreadInfo` là một hướng đọc stack của **platform thread** khác, nhưng **không phải API toàn diện cho virtual threads**. Nếu tool chỉ báo Java application thread frames và bỏ implementation-specific frames, kết luận nên là **“công cụ này không hiện frame”**, không phải **“hidden class không được thực thi”**.

### Bước 5: đặt ranh giới an toàn cho logging

Thread dumps/stack traces có thể tiết lộ **tên class, đường dẫn source, lược đồ nghiệp vụ, lock object, request context và cấu trúc hệ thống**. Chúng có thể rất lớn và có chi phí khi thu thập ở production. Cần có:

- phân quyền collect, lưu và xem thread dumps/JFR;
- thời hạn lưu, dung lượng, giám sát overhead;
- loại bỏ/ẩn danh request payload/token/secrets khỏi logging hoặc correlations;
- hạn chế sampling, kích thước stack, tần suất snapshot;
- chỉ bật class-loading debug logs mức chi tiết cần thiết khi điều tra.

Không in bytecode hoặc toàn bộ nội dung lớp sinh động ra log ứng dụng nếu không có nhu cầu và kiểm soát truy cập. Việc “hidden” trong **hidden class** **không phải tính năng bảo mật để giấu mã độc hoặc che giấu hành vi**.

## 8. Các lỗi phổ biến

| Nhầm lẫn | Điều đúng / cách xử lý |
| --- | --- |
| Không thấy `/0x...` trong Throwable nên chắc không có hidden class | JVM có thể lọc hidden frames. Dùng `StackWalker SHOW_HIDDEN_FRAMES` trong thread liên quan hoặc công cụ quan sát phù hợp. |
| `SHOW_HIDDEN_FRAMES` và `Class.isHidden()` là một chức năng | Một bên là option hiển thị **stack frames**, bên kia kiểm tra loại **Class<?>`. |
| `StackWalker` mặc định đã hiển thị mọi frame | Mặc định lọc các hidden frames/implementation frames. |
| Gọi `getDeclaringClass()` trên StackWalker không có `RETAIN_CLASS_REFERENCE` | Có thể ném `UnsupportedOperationException`; thêm option khi cần Class object. |
| Tên `Generated/0x...` đưa vào `Class.forName` sẽ tải lại lớp | Hidden class không có binary name có thể tra cứu kiểu đó. |
| Dùng suffix `/0x...` làm ID bền vững | Hậu tố động và không phù hợp làm database key/correlation ID lâu dài. |
| StackWalker từ thread main sẽ thấy stack của worker | Không. StackWalker quan sát **current thread**; dùng thread diagnostics cho worker. |
| `ThreadMXBean.dumpAllThreads` chắc chứa virtual threads trên JDK 21+ | Không. ThreadMXBean quản lý platform threads; dùng dump dành cho virtual threads theo JDK. |
| Thread dump không hiện hidden class nghĩa là lớp đã unload | Thread dump chỉ là snapshot một thời điểm, có thể lọc frame; không kết luận vòng đời class. |
| `Unknown Source` nghĩa là không có code chạy | Bytecode lớp động có thể không chứa `SourceFile/LineNumberTable`. |
| `... N more` của stack trace nghĩa là JVM giấu hidden frames | Nó thường là cách formatter rút gọn các khung chung của nested causes. |
| Chụp stack sau sự cố rồi cho rằng đó là stack lúc lỗi | Thread có thể đã chạy tiếp; dùng exception trace, JFR, application correlation và snapshot đúng thời điểm. |
| Dùng API `Unsafe.defineAnonymousClass` cũ vì nghe “anonymous” | Đây là kỹ thuật nội bộ/lỗi thời, không phải API được khuyến nghị cho Java 15+. Dùng `Lookup.defineHiddenClass`. |
| Thu liên tục full dump để chắc chắn không bỏ sót | Dễ tạo overhead và rủi ro dữ liệu; dùng sampling/JFR và instrumentation theo nhu cầu. |

## 9. Checklist thực hành và tài liệu chuẩn

Trước khi kết luận nguyên nhân lỗi có liên quan đến hidden class:

1. Xác định JVM version, framework/generator và bối cảnh vì sao lớp được sinh động.
2. Nếu có `Class<?>`, kiểm tra **`isHidden()`** thay vì regex tên.
3. Không giả định tên `Class.getName()` của hidden class là binary name.
4. Phân biệt **exception stack**, **current-thread StackWalker**, **cross-thread dump** và **JFR events**.
5. Khi cần hidden frames trong current thread, bật `SHOW_HIDDEN_FRAMES`; khi cần `getDeclaringClass()`, bật `RETAIN_CLASS_REFERENCE`.
6. Kiểm tra cause/suppressed của Throwable và cấu hình formatter/logger.
7. Khi điều tra thread khác, dùng `ThreadMXBean` hoặc `jcmd`, chụp đúng thời điểm/số lần thích hợp.
8. Với virtual threads trên JDK 21+, dùng công cụ dump hỗ trợ chúng, không chỉ `ThreadMXBean`.
9. Ghi request/job correlation, generated-handler ID và source mapping; đừng dựa vào hậu tố tên động.
10. Xác minh các khác biệt giữa công cụ trên đúng JDK build đang triển khai.
11. Không xem sự **vắng mặt của frame** như bằng chứng **không có hidden class**.
12. Giới hạn overhead, bảo vệ dữ liệu nhạy cảm và phạm vi lưu trữ dump/log.

### Tài liệu chính thức còn áp dụng

- [JEP 371 — Hidden Classes](https://openjdk.org/jeps/371): hidden classes chính thức từ Java 15.
- [Java SE 26 — Class, mục Hidden Classes](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Class.html): `Class.isHidden` và tên lớp ẩn không phải binary name.
- [Java SE 26 — MethodHandles.Lookup](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): `defineHiddenClass`, `ClassOption.NESTMATE` và `STRONG`.
- [Java SE 26 — StackWalker](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/StackWalker.html): stack walking và giới hạn current thread.
- [Java SE 26 — StackWalker.Option](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/StackWalker.Option.html): `SHOW_HIDDEN_FRAMES`, `RETAIN_CLASS_REFERENCE`.
- [Java SE 26 — ThreadMXBean](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/ThreadMXBean.html): thread info và phạm vi platform threads.
- [Java SE 25 — jcmd Utility](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html): `Thread.print`, `Thread.dump_to_file`.
- [Java SE 26 — Virtual Threads and Diagnostics](https://docs.oracle.com/en/java/javase/26/core/virtual-threads.html): thread dump bao gồm virtual threads ở runtime hỗ trợ.
- [Java SE 26 — StackTraceElement](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/StackTraceElement.html): tên lớp, file nguồn, số dòng và module/class loader.
- [Oracle JDK 15 Release Notes — JEP 371](https://www.oracle.com/java/technologies/javase/15-relnote-issues.html): hành vi `Class.getName()` của hidden class chứa dấu `/`.

**Kết luận:** hidden class trong Java 15+ có thể bị **lọc khỏi một số stack trace thông thường**. Để chẩn đoán chính xác, xác nhận lớp bằng **`Class.isHidden()`**, dùng **`StackWalker.SHOW_HIDDEN_FRAMES`** và `RETAIN_CLASS_REFERENCE` trong đường gọi cần quan sát, kết hợp **thread dumps/ThreadMXBean/JFR** theo loại thread và phiên bản JVM. Không suy ra lớp ẩn “không tồn tại” chỉ vì một công cụ không hiển thị frame.