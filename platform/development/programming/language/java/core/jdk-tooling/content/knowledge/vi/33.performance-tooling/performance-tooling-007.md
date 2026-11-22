# Profiling instrumentation trong Java

Profiling instrumentation là kỹ thuật bổ sung cơ chế quan sát vào ứng dụng hoặc JVM để thu thập dữ liệu hiệu năng như thời gian thực thi, số lần gọi, allocation, lock wait và các sự kiện runtime. Dữ liệu này giúp xác định method, thread, class hoặc thành phần đang tiêu tốn tài nguyên.

Trong Java 17+, có nhiều lớp công cụ: Java agent và Instrumentation API để quan sát hoặc biến đổi bytecode; JVM Tool Interface (JVMTI) để xây native agent; Java Flight Recorder (JFR) để thu thập event và sample; JMX để đọc metric tổng hợp. Chọn đúng cơ chế giúp thu được bằng chứng cần thiết với overhead có thể kiểm soát.

## 1. Profiling và instrumentation là gì?

**Profiling** là quá trình đo và phân tích hành vi runtime để hiểu ứng dụng sử dụng CPU, bộ nhớ, thread và I/O như thế nào.

**Instrumentation** là việc thêm mã hoặc hook quan sát vào chương trình để thu thập dữ liệu. Ví dụ:

- Ghi thời gian bắt đầu/kết thúc một thao tác.
- Đếm số lần một method được gọi.
- Ghi nhận class được nạp.
- Phát JFR event khi một nghiệp vụ quan trọng hoàn thành.
- Chèn bytecode để đo thời gian method hoặc theo dõi lời gọi.
- Nhận event từ JVM về thread, GC, monitor hoặc compilation.

Instrumentation có thể được thực hiện trực tiếp trong source code, qua Java agent, bằng native agent hoặc thông qua event framework đã có sẵn trong JVM.

Mục tiêu là tạo dữ liệu đủ để trả lời một câu hỏi hiệu năng cụ thể. Không nên instrument mọi method và mọi object ngay từ đầu, vì lượng dữ liệu và overhead có thể làm thay đổi hành vi đang đo.

## 2. Phân biệt sampling và instrumentation

Hai cách phổ biến để quan sát code execution là sampling và instrumentation.

| Đặc điểm | Sampling profiler | Instrumentation profiler |
|---|---|---|
| Cách hoạt động | Lấy mẫu stack/thread theo chu kỳ hoặc sự kiện | Chèn hook vào method/event để ghi nhận hoạt động |
| Phạm vi | Các vị trí được sample trong khoảng quan sát | Những method/event đã được instrument |
| Độ chi tiết | Thống kê, không thấy mọi lời gọi | Có thể thấy từng lần gọi hoặc từng event |
| Overhead | Thường thấp hơn khi sampling hợp lý | Có thể tăng nhanh nếu instrument method tần suất cao |
| Phù hợp | Tìm CPU hotspot, call tree, hành vi tổng thể | Đo một nghiệp vụ cụ thể, đếm invocation, trace có chọn lọc |
| Giới hạn | Có thể bỏ lỡ method ngắn hoặc ít xuất hiện | Hook có thể làm thay đổi thời gian và hành vi được đo |

Sampling trả lời câu hỏi “thread thường ở đâu khi được lấy mẫu?”. Instrumentation trả lời câu hỏi “những method/event đã chọn xảy ra bao nhiêu lần và mất bao lâu?”.

Không có kỹ thuật nào luôn chính xác hơn. Hãy bắt đầu bằng sampling để khoanh vùng hotspot; sau đó instrument có chọn lọc khi cần số liệu chi tiết cho một luồng nghiệp vụ.

## 3. Các cơ chế profiling trong Java

| Cơ chế | Cấp độ | Trường hợp sử dụng |
|---|---|---|
| JFR | Event và sampling tích hợp trong JVM | CPU, allocation, GC, lock, I/O, custom event |
| Java agent / Instrumentation API | Java bytecode | Theo dõi class load hoặc biến đổi method |
| JVMTI | Native JVM interface | Profiler/native tooling cần event và quyền kiểm soát sâu |
| JMX / MXBean | Metric quản lý JVM/ứng dụng | Thread count, heap, GC count, uptime, metric tổng hợp |
| Instrumentation trong source | Code ứng dụng | Đo nghiệp vụ, request stage, queue hoặc dependency cụ thể |
| JMH | Benchmark framework | So sánh hiệu năng một đoạn code trong môi trường benchmark có kiểm soát |

JFR và JMC thường là lựa chọn đầu tiên để điều tra production vì đã có sẵn nhiều event runtime. Java agent phù hợp khi cần quan sát hoặc biến đổi bytecode. JVMTI dành cho công cụ native cần quyền truy cập sâu hơn. JMX cung cấp metric tổng hợp, còn JMH dùng để benchmark và kiểm tra thay đổi trong môi trường thử nghiệm.

## 4. Java agent hoạt động như thế nào?

Java agent là một JAR được JVM nạp theo yêu cầu. Agent có thể nhận đối tượng **Instrumentation** để đăng ký class transformer, xem thông tin class và yêu cầu JVM retransformation/redefinition khi runtime hỗ trợ.

Có hai entry point thường gặp:

- **premain(String agentArgs, Instrumentation inst):** agent được nạp lúc khởi chạy JVM bằng **-javaagent**.
- **agentmain(String agentArgs, Instrumentation inst):** agent được nạp sau khi JVM đã chạy, nếu runtime và chính sách cho phép dynamic attach.

Khi khởi chạy bằng **-javaagent**, JVM gọi **premain** trước **main** của ứng dụng. Agent JAR phải khai báo **Premain-Class** trong manifest.

Ví dụ:

~~~powershell
java -javaagent:profiling-agent.jar -jar application.jar
~~~

Có thể truyền chuỗi tùy chọn:

~~~powershell
java -javaagent:profiling-agent.jar=include=demo,verbose=true -jar application.jar
~~~

Agent nhận toàn bộ phần sau dấu bằng trong tham số agentArgs; việc phân tích chuỗi tùy chọn do agent tự thực hiện.

Nếu premain ném exception không được xử lý, JVM có thể dừng khởi động ứng dụng. Vì vậy, agent production cần khởi tạo gọn, xử lý lỗi rõ ràng và tránh làm hỏng startup chỉ vì một metric không quan trọng.

## 5. Instrumentation API và ClassFileTransformer

API nằm trong module **java.instrument**, package **java.lang.instrument**.

Các thành phần quan trọng:

- **Instrumentation:** cung cấp các dịch vụ instrument chương trình đang chạy trong JVM.
- **ClassFileTransformer:** nhận bytecode khi class được load, redefine hoặc retransform.
- **addTransformer(...):** đăng ký transformer.
- **retransformClasses(...):** yêu cầu JVM áp dụng lại transformer cho class đã load nếu được hỗ trợ.
- **redefineClasses(...):** thay định nghĩa class bằng bytecode mới nếu được hỗ trợ.
- **isModifiableClass(...):** kiểm tra class có thể sửa hay không.

ClassFileTransformer.transform(...) nhận class name, class loader, protection domain và byte array của class file. Transformer có thể trả về bytecode đã biến đổi. Nếu trả về null, class được giữ nguyên từ góc nhìn của transformer đó.

Một transformer chỉ quan sát class load có thể đếm hoặc ghi tên class. Để đo thời gian từng method, agent phải chèn bytecode gọi hook ở method entry/exit, thường sử dụng thư viện bytecode như ASM hoặc Byte Buddy.

### 5.1. Load-time và retransformation

**Load-time transformation** diễn ra khi JVM nạp class. Đây là cơ hội thuận tiện để xử lý bytecode trước khi class được định nghĩa.

**Retransformation** áp dụng lại transformer cho class đã được nạp. Agent cần khai báo khả năng retransformation trong manifest và kiểm tra Instrumentation.isRetransformClassesSupported() trước khi gọi API.

Một số thay đổi cấu trúc class bị giới hạn. Retransformation/redefinition thông thường không phải cơ chế để tùy ý thêm/xóa field hoặc method, đổi chữ ký method hay thay đổi quan hệ kế thừa. Cần tuân thủ các giới hạn của Instrumentation API và JVM.

### 5.2. Manifest của agent

Ví dụ manifest tối thiểu:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.ProfilingAgent
~~~

Nếu agent cần retransformation, có thể khai báo thêm:

~~~text
Can-Retransform-Classes: true
~~~

Nếu cần redefine class, khai báo Can-Redefine-Classes: true và kiểm tra runtime có hỗ trợ hay không. Không khai báo capability mà agent không dùng.

## 6. Ví dụ Java agent quan sát class load

Ví dụ này đăng ký một transformer để đếm class thuộc package demo. Nó minh họa vòng đời agent và callback của ClassFileTransformer. Transformer trả về null, vì vậy ví dụ chỉ quan sát class load, chưa chèn bytecode đo thời gian method.

Tạo file src/demo/ProfilingAgent.java:

~~~java
package demo;

import java.lang.instrument.Instrumentation;
import java.util.concurrent.atomic.AtomicInteger;

public final class ProfilingAgent {
    public static void premain(String agentArgs, Instrumentation inst) {
        AtomicInteger observed = new AtomicInteger();

        inst.addTransformer((loader, className, classBeingRedefined,
                             protectionDomain, classfileBuffer) -> {
            if (className != null && className.startsWith("demo/")) {
                int count = observed.incrementAndGet();
                if (count <= 10) {
                    System.out.println("[agent] observed "
                            + className.replace('/', '.'));
                }
            }
            return null;
        });

        Runtime.getRuntime().addShutdownHook(new Thread(
                () -> System.out.println(
                        "[agent] demo classes observed: " + observed.get()),
                "profiling-agent-summary"
        ));
    }
}
~~~

Tạo manifest manifest.mf:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.ProfilingAgent

~~~

Tạo file ứng dụng src/demo/TargetApp.java:

~~~java
package demo;

public final class TargetApp {
    public static void main(String[] args) {
        for (int i = 0; i < 3; i++) {
            process(i);
        }
        System.out.println("Application completed.");
    }

    private static void process(int id) {
        String payload = "task-" + id;
        System.out.println("processed " + payload);
    }
}
~~~

Biên dịch agent và ứng dụng:

~~~powershell
javac -d agent-classes src/demo/ProfilingAgent.java
jar --create --file profiling-agent.jar --manifest manifest.mf -C agent-classes .
javac -d app-classes src/demo/TargetApp.java
~~~

Chạy:

~~~powershell
java -javaagent:profiling-agent.jar -cp app-classes demo.TargetApp
~~~

Với chương trình mẫu chỉ có một class ứng dụng trong package demo, output có dạng:

~~~text
[agent] observed demo.TargetApp
processed task-0
processed task-1
processed task-2
Application completed.
[agent] demo classes observed: 1
~~~

Thứ tự thông báo class có thể thay đổi khi ứng dụng có nhiều class hoặc nhiều thread nạp class đồng thời. Ví dụ này không đo method duration. Để đo từng method, cần biến đổi bytecode và chèn hook entry/exit, hoặc dùng JFR custom event/source instrumentation.

## 7. Bytecode instrumentation để đo method

Một profiler dùng bytecode instrumentation thường thực hiện các bước:

1. Chọn class/method cần instrument theo package, annotation hoặc cấu hình.
2. Transformer đọc class file.
3. Thư viện bytecode thêm hook ở đầu method.
4. Hook lưu timestamp hoặc bắt đầu event.
5. Hook ở mọi đường thoát của method ghi duration và trạng thái hoàn thành.
6. Transformer trả bytecode mới để JVM định nghĩa class.

Một phép đo method duration phải xử lý cả return bình thường và exception. Nếu chỉ thêm hook ở cuối method, exception sẽ làm mất event kết thúc. Bytecode thường cần try/finally tương đương để đóng event trên mọi đường thoát.

Các thư viện thường dùng:

- **ASM:** thư viện thao tác bytecode cấp thấp, kiểm soát chi tiết instruction và stack frame.
- **Byte Buddy:** API cấp cao hơn để tạo và biến đổi class/method.
- **Javassist:** thư viện hỗ trợ chỉnh sửa bytecode qua API hướng source hơn.

Các thư viện này không thuộc JDK chuẩn. Cần khai báo dependency, đóng gói agent và kiểm thử tương thích với JDK, class loader và framework của ứng dụng.

### 7.1. Inclusive và exclusive time

Nếu method A gọi B rồi C:

- **Inclusive time của A** gồm thời gian A và các method con được gọi bên trong.
- **Exclusive/self time của A** là phần thời gian A tự thực hiện, loại trừ thời gian các method con.

Nếu cộng inclusive time của tất cả method, cùng một khoảng thời gian có thể bị đếm nhiều lần. Khi đọc profile tree, phải biết cột đang hiển thị inclusive hay self time.

### 7.2. Đếm invocation và duration

Profiler có thể thu thập invocation count, total duration, average duration, min/max duration và error count. Có thể thêm tag như endpoint, operation type hoặc workload class nếu cần.

Average có thể che khuất tail latency. Nếu method có phân phối thời gian lệch, hãy xem histogram hoặc percentile như p50, p95 và p99 thay vì chỉ nhìn trung bình.

## 8. JFR: profiling tích hợp trong JVM

Java Flight Recorder là framework thu thập event runtime tích hợp trong JVM. JFR có các event phục vụ chẩn đoán CPU, thread, allocation, GC, lock, I/O và nhiều hoạt động khác.

JFR hỗ trợ hai cách thu thập chính:

- Event tức thời: ghi nhận một sự kiện xảy ra tại một thời điểm.
- Event có duration: gọi begin() và end() để đo khoảng thời gian.

JFR cũng có event sampling như jdk.ExecutionSample và jdk.ObjectAllocationSample. Sampling hữu ích để tìm hotspot mà không phải chèn hook vào mọi method.

Có thể bắt đầu recording khi JVM khởi chạy:

~~~powershell
java -XX:StartFlightRecording=name=profile,settings=profile,duration=60s,filename=profile.jfr -jar application.jar
~~~

Với JVM đang chạy:

~~~powershell
jcmd <PID> JFR.start name=profile settings=profile duration=60s filename=profile.jfr
jcmd <PID> JFR.check
~~~

Dump recording đang chạy:

~~~powershell
jcmd <PID> JFR.dump name=profile filename=profile-snapshot.jfr
~~~

Dừng recording:

~~~powershell
jcmd <PID> JFR.stop name=profile
~~~

Mở file trong JDK Mission Control (JMC) để xem method profiling, allocation, locks, threads, I/O và GC. JMC là công cụ riêng; không phải mọi bản JDK đều cài sẵn JMC.

## 9. Tạo custom JFR event để instrument nghiệp vụ

Khi cần đo một operation nghiệp vụ, có thể định nghĩa event riêng bằng cách kế thừa jdk.jfr.Event.

Một custom event có thể chứa tên operation, kích thước đầu vào, trạng thái hoàn thành, mã kết quả không nhạy cảm và duration từ begin() tới end(). Có thể bật stack trace nếu recording settings yêu cầu.

Dùng annotation để đặt tên, label, category và mô tả event. Field phải có kiểu được JFR hỗ trợ. Tránh đưa password, token, nội dung request nhạy cảm hoặc identifier cá nhân vào payload.

### 9.1. Event.begin, end, commit và shouldCommit

- begin() đánh dấu thời điểm bắt đầu event duration.
- end() đánh dấu thời điểm kết thúc.
- commit() gửi event vào recording.
- isEnabled() kiểm tra event có đang được bật không.
- shouldCommit() kiểm tra event có đủ điều kiện ghi theo settings hiện tại không.

Có thể dùng isEnabled() để tránh thu thập payload tốn kém khi event bị tắt. Sau khi kết thúc event, gọi shouldCommit() trước commit() khi muốn tránh chuẩn bị/ghi dữ liệu không cần thiết.

## 10. Ví dụ Java 17+: custom JFR event chạy được

Tạo file ProfilingEventDemo.java:

~~~java
import java.nio.file.Path;
import java.time.Duration;
import jdk.jfr.Category;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;

public final class ProfilingEventDemo {
    @Name("com.example.WorkUnit")
    @Label("Work Unit")
    @Category({"Application", "Profiling"})
    public static final class WorkUnitEvent extends Event {
        @Label("Work ID")
        int workId;

        @Label("Input Size")
        int inputSize;

        @Label("Result")
        long result;
    }

    private static long processWork(int workId) {
        long sum = 0;
        for (int i = 1; i <= 200_000; i++) {
            sum += (i * 31L + workId) % 97;
        }
        return sum;
    }

    public static void main(String[] args) throws Exception {
        try (Recording recording = new Recording()) {
            recording.setName("profiling-instrumentation");
            recording.enable(WorkUnitEvent.class)
                    .withThreshold(Duration.ZERO)
                    .withStackTrace();
            recording.start();

            for (int id = 1; id <= 5; id++) {
                WorkUnitEvent event = new WorkUnitEvent();
                if (event.isEnabled()) {
                    event.workId = id;
                    event.inputSize = 200_000;
                    event.begin();
                    event.result = processWork(id);
                    event.end();

                    if (event.shouldCommit()) {
                        event.commit();
                    }
                }
            }

            recording.stop();
            recording.dump(Path.of("profiling-events.jfr"));
        }

        System.out.println("Work units processed: 5");
        System.out.println("Recording written: profiling-events.jfr");
    }
}
~~~

Biên dịch và chạy trên JDK 17:

~~~powershell
javac --add-modules jdk.jfr ProfilingEventDemo.java
java --add-modules jdk.jfr ProfilingEventDemo
~~~

Stdout:

~~~text
Work units processed: 5
Recording written: profiling-events.jfr
~~~

Kiểm tra recording:

~~~powershell
jfr summary profiling-events.jfr
jfr print --events com.example.WorkUnit profiling-events.jfr
~~~

Trong JMC, tìm event **Work Unit** thuộc category **Application / Profiling**. Mỗi event chứa work ID, input size, result, duration và stack trace. Ví dụ này instrument đúng năm operation đã chọn; event count không phụ thuộc method sampling.

Duration.ZERO giúp recording demo ghi cả operation ngắn. Với production, hãy cân nhắc threshold phù hợp và chỉ bật event cần thiết để tránh tạo recording quá lớn.

## 11. JMX và MXBean: metric tổng hợp

JMX (Java Management Extensions) cung cấp giao diện quản lý và giám sát JVM/ứng dụng. Các platform MXBean có sẵn trong ManagementFactory:

- ThreadMXBean: thread count, peak, daemon và thông tin thread.
- MemoryMXBean: heap/non-heap usage.
- ClassLoadingMXBean: số class đang nạp, tổng số đã nạp và unload.
- GarbageCollectorMXBean: collection count và collection time.
- RuntimeMXBean: uptime, VM arguments và thông tin runtime.
- CompilationMXBean: tổng compile time nếu runtime hỗ trợ.

JMX hữu ích để theo dõi metric theo thời gian và tạo dashboard/alert. Nó không tự cung cấp call tree chi tiết cho từng method. Khi cần biết method nào tạo CPU hotspot, dùng JFR hoặc profiler.

Có thể kết hợp JMX với JFR: metrics cho biết lúc nào có bất thường; recording cho biết thread/event/stack nào có thể giải thích bất thường đó.

## 12. JVMTI: native profiling agent

JVMTI (JVM Tool Interface) là native interface dành cho công cụ cần kiểm tra hoặc điều khiển trạng thái JVM. Agent JVMTI thường viết bằng C/C++ và dùng header jvmti.h trong JDK.

JVMTI cung cấp event callbacks cho class load, thread, method/compiled method và nhiều hoạt động VM; truy vấn thread, stack frame, monitor và heap theo capability; hook để quan sát class file load và instrument bytecode.

Native agent có thể được nạp bằng:

~~~powershell
java -agentlib:profiler -jar application.jar
~~~

Hoặc chỉ định đường dẫn thư viện:

~~~powershell
java -agentpath:C:\tools\profiler.dll -jar application.jar
~~~

Trên Linux, thư viện native thường có đuôi .so; trên macOS có thể là .dylib. Tên và đường dẫn phụ thuộc nền tảng.

JVMTI không phải Java agent. Nó yêu cầu native library, toolchain C/C++ và hiểu biết về JNI/JVM lifecycle. Không phải mọi implementation JVM đều hỗ trợ toàn bộ JVMTI. Chọn JVMTI khi cần native profiler hoặc khả năng quan sát mà JFR/Java agent không đáp ứng.

## 13. JMH không phải profiler

JMH (Java Microbenchmark Harness) là framework để đo hiệu năng microbenchmark. JMH giúp quản lý warm-up, fork, iteration, dead-code elimination và các yếu tố dễ làm sai kết quả benchmark.

Phân biệt:

- Profiler trả lời ứng dụng đang tiêu tốn thời gian/tài nguyên ở đâu.
- Instrumentation thêm dữ liệu quan sát vào method hoặc operation.
- JMH đo thời gian/throughput của đoạn code trong benchmark có kiểm soát.

Có thể chạy JMH cùng profiler để tìm nguyên nhân một benchmark chậm, nhưng kết quả benchmark không thay thế recording production. Không dùng một vòng lặp System.nanoTime() đơn giản để thay thế JMH khi cần so sánh microbenchmark nghiêm túc.

## 14. Đo thời gian đúng cách

Khi instrument thủ công, dùng System.nanoTime() để đo khoảng thời gian. Không dùng System.currentTimeMillis() cho duration ngắn vì đây là đồng hồ thời gian thực có thể bị điều chỉnh.

Ví dụ:

~~~java
long start = System.nanoTime();
try {
    performOperation();
} finally {
    long elapsedNanos = System.nanoTime() - start;
    recordDuration(elapsedNanos);
}
~~~

nanoTime() là đồng hồ đơn điệu phù hợp để đo chênh lệch thời gian; không dùng giá trị tuyệt đối của nó làm timestamp ngày giờ.

Nếu đo method có thể ném exception, đặt phần ghi duration trong finally. Nếu có nested method, quyết định rõ muốn đo inclusive hay exclusive time. Với async code, method return có thể chỉ đánh dấu lúc tạo task, không phải lúc công việc hoàn tất; hãy instrument điểm bắt đầu/kết thúc thực sự của operation.

## 15. Overhead và observer effect

Instrumentation tiêu thụ CPU, bộ nhớ và có thể làm thay đổi thời gian của ứng dụng. Đây là observer effect: công cụ quan sát tác động tới hệ thống đang đo.

Nguồn overhead thường gặp:

- Gọi hook ở mỗi method invocation.
- Lấy timestamp quá thường xuyên.
- Tạo object/event/string cho mỗi lần gọi.
- Ghi log đồng bộ trong callback.
- Khóa dùng chung để cập nhật counter.
- Thu thập stack trace hoặc payload lớn.
- Instrument cả JDK, framework và thư viện thay vì chỉ package cần điều tra.

Cách giảm overhead:

1. Chọn một câu hỏi và instrument đúng điểm cần đo.
2. Ưu tiên JFR sampling để khoanh vùng trước.
3. Lọc package/class/method; không instrument toàn bộ classpath.
4. Dùng counter hiệu quả như LongAdder khi có nhiều thread cập nhật.
5. Không ghi log đồng bộ trên hot path.
6. Dùng isEnabled()/shouldCommit() cho custom JFR event.
7. Giới hạn thời gian recording và event threshold.
8. So sánh throughput/latency khi bật và tắt profiler.

Đừng mặc định profiler “zero overhead”. Đo tác động trên workload đại diện và ghi rõ cấu hình instrumentation cùng kết quả.

## 16. Pitfall khi instrument method và bytecode

### 16.1. Exception và mọi đường thoát

Hook kết thúc phải chạy khi method return bình thường hoặc ném exception. Bytecode transformer cần xử lý tất cả return opcode và exception handler; thiếu một đường thoát sẽ làm event không được đóng hoặc counter sai.

### 16.2. Recursion và reentrancy

Nếu hook gọi lại method đã instrument, profiler có thể tự tạo vòng lặp. Dùng guard/reentrancy flag phù hợp, tránh instrument package của agent và tránh gọi API phức tạp từ transformer.

### 16.3. Class loader và module

Agent có thể gặp nhiều class loader và module khác nhau. Class hỗ trợ của agent không nhất thiết nhìn thấy từ mọi loader. Instrument bootstrap class hoặc module có thể cần điều chỉnh module read/open và bootstrap search path; đây là vùng dễ gây lỗi và nên chỉ làm khi thực sự cần.

### 16.4. Concurrency trong transformer

JVM có thể gọi transformer đồng thời từ nhiều thread. Transformer nên thread-safe, không giữ lock lâu, không thực hiện I/O nặng và không gây class loading đệ quy trong lúc transform.

### 16.5. JIT và method inlining

JIT có thể inline method hoặc biên dịch code theo cách khiến stack trace/profiling view khác với cấu trúc source. Profiler cần hiểu event đang hiển thị interpreted frame, compiled frame hay inlined frame. Không giả định mọi method call đều xuất hiện như một frame độc lập.

## 17. Chọn công cụ theo câu hỏi

| Câu hỏi | Cơ chế nên bắt đầu |
|---|---|
| Method nào thường dùng CPU? | JFR execution sampling / sampling profiler |
| Class/stack nào tạo nhiều allocation? | JFR allocation events |
| Thread nào chờ lock? | JFR monitor/park events và JMC |
| Một nghiệp vụ cụ thể mất bao lâu? | Custom JFR event hoặc source instrumentation |
| Muốn quan sát class được nạp? | Java agent + ClassFileTransformer |
| Cần sửa bytecode để đo invocation? | Java agent + ASM/Byte Buddy |
| Cần native stack/JVM-level hook sâu? | JVMTI/native profiler |
| Muốn dashboard heap/thread/GC count? | JMX/MXBean |
| Muốn so sánh hai thuật toán trong benchmark? | JMH |

Một quy trình thực tế là dùng JFR/JMC để khoanh vùng, thêm custom event hoặc agent cho đúng operation, sau đó dùng JMH để benchmark thay đổi trong môi trường kiểm soát.

## 18. Troubleshooting

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Failed to find Premain-Class | Manifest thiếu hoặc sai Premain-Class | Kiểm tra manifest bên trong agent JAR |
| ClassNotFoundException cho agent | JAR không chứa class hoặc package sai | Kiểm tra cấu trúc JAR và tên class đầy đủ |
| JVM dừng ngay lúc startup | premain ném exception hoặc agent init thất bại | Ghi lỗi rõ ràng, kiểm tra dependency và startup log |
| Transformer không được gọi | Agent đăng ký sau khi class đã load hoặc filter quá hẹp | Đăng ký sớm bằng premain, kiểm tra internal class name dạng pkg/Class |
| Transformer chạy nhưng method không được đo | Transformer chỉ quan sát class hoặc trả bytecode gốc | Tích hợp bytecode library và chèn hook entry/exit |
| retransformClasses thất bại | Capability không bật hoặc class không modifiable | Kiểm tra manifest, isRetransformClassesSupported() và isModifiableClass() |
| Custom JFR event không xuất hiện | Event chưa enable, không commit hoặc threshold không phù hợp | Kiểm tra isEnabled, shouldCommit, settings và jfr summary |
| Duration sai hoặc event bị thiếu | Không xử lý exception/nested/async completion | Dùng finally, xác định boundary đúng và kiểm tra mọi đường thoát |
| CPU tăng khi bật agent | Instrument quá rộng hoặc hook quá nặng | Giới hạn phạm vi, giảm allocation/logging và đo overhead |
| Class loading lỗi sau khi instrument | Bytecode/frame/module/classloader không hợp lệ | Kiểm tra transformer, verifier và tương thích JDK/thư viện |

## 19. Bảo mật và vận hành

Agent và profiler chạy trong cùng tiến trình với ứng dụng và có thể truy cập dữ liệu runtime. Chỉ nạp agent JAR/native library từ nguồn đáng tin cậy.

- Kiểm tra nguồn gốc và nội dung agent JAR trước khi triển khai.
- Giới hạn quyền ghi file recording và log.
- Không ghi secret, token, nội dung request hoặc dữ liệu cá nhân vào custom event.
- Hạn chế dynamic attach theo chính sách runtime và môi trường.
- Dùng quyền JMX phù hợp; không mở endpoint quản lý ra mạng không tin cậy.
- Ghi lại phiên bản JDK, agent, dependency bytecode và cấu hình profiler.
- Có cách tắt agent/recording an toàn nếu overhead hoặc lỗi xuất hiện.

## 20. Quy trình triển khai profiling instrumentation

1. Xác định triệu chứng và câu hỏi cần trả lời.
2. Chọn sampling, JFR event, Java agent, JVMTI hay JMX phù hợp.
3. Bắt đầu với phạm vi nhỏ và thời lượng giới hạn.
4. Xác nhận dữ liệu có timestamp, thread, stack và field cần thiết.
5. Đo overhead bằng workload đại diện.
6. Đối chiếu số liệu với baseline và metrics độc lập.
7. Chỉ mở rộng instrumentation khi bằng chứng ban đầu chưa đủ.
8. Kiểm tra exception, recursion, async completion và thread safety.
9. Thử trên staging/canary trước khi triển khai rộng.
10. Ghi lại cấu hình, kết quả và cách rollback/tắt instrumentation.

## 21. Checklist profiling instrumentation

- [ ] Đã xác định câu hỏi hiệu năng cụ thể.
- [ ] Đã phân biệt sampling với bytecode/source instrumentation.
- [ ] Đã chọn đúng cơ chế: JFR, Java agent, JVMTI, JMX hoặc JMH.
- [ ] Java agent có manifest và entry point đúng.
- [ ] Transformer lọc đúng class và xử lý thread-safe.
- [ ] Bytecode instrumentation xử lý return, exception và mọi đường thoát.
- [ ] Đã xác định inclusive/exclusive time và invocation count.
- [ ] Custom JFR event có field hữu ích, label và category rõ ràng.
- [ ] Đã dùng isEnabled()/shouldCommit() khi phù hợp.
- [ ] Đã đo duration bằng System.nanoTime() hoặc JFR duration.
- [ ] Đã kiểm tra overhead và observer effect.
- [ ] Đã kiểm tra class loader, module, recursion và JIT behavior.
- [ ] Đã bảo vệ recording, agent và dữ liệu nhạy cảm.
- [ ] Đã so sánh kết quả với baseline/workload tương đương.
- [ ] Đã có cách tắt hoặc rollback instrumentation.

Profiling instrumentation bổ sung dữ liệu để hiểu hành vi runtime. Sampling như JFR giúp tìm hotspot với chi phí thường thấp; Java agent và JVMTI cho phép instrument sâu hơn; custom JFR event đo đúng operation nghiệp vụ; JMX theo dõi metric tổng hợp và JMH kiểm chứng microbenchmark. Hãy bắt đầu bằng câu hỏi cụ thể, giới hạn phạm vi, đo overhead và phân biệt dữ liệu quan sát được với kết luận suy ra từ dữ liệu.

## Tài liệu tham khảo

- Oracle, Java SE 17 API — java.lang.instrument package: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html
- Oracle, Java SE 17 API — Instrumentation: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html
- Oracle, Java SE 17 Specification — JVM Tool Interface (JVMTI): https://docs.oracle.com/en/java/javase/17/docs/specs/jvmti.html
- Oracle, Java SE 17 API — jdk.jfr package: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/package-summary.html
- Oracle, Java SE 17 — The jcmd Command: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html
- Oracle, JDK Mission Control 9 User Guide: https://docs.oracle.com/en/java/java-components/jdk-mission-control/9/user-guide/jdk-mission-control.html
