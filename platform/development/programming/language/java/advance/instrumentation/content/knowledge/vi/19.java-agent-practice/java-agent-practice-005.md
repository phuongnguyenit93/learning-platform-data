# Đo thời gian phương thức cho cả đường trả về và đường ném ngoại lệ

## 1. Mục tiêu thực nghiệm: mỗi lần gọi có đúng một kết thúc

Khi một Java agent đo thời gian thực thi phương thức, **chỉ chèn điểm đo trước `return` là không đủ**. Phương thức có thể thoát bằng một `return` bình thường, nhưng cũng có thể ném ngoại lệ trực tiếp (`throw`), ném ngoại lệ ngầm từ JVM (như chia cho 0, `NullPointerException`), hoặc nhận ngoại lệ từ method được gọi bên trong.

Bài thực nghiệm thuộc nhóm **Thực nghiệm agent**. Ta sẽ tự tạo một **Java agent bằng Class-File API trên JDK 24** để chèn:

- `TimingProbe.enter()` vào đầu method, lưu mốc `System.nanoTime()`;
- `TimingProbe.success()` ngay trước mọi instruction `return`;
- `TimingProbe.failure()` trong **exception handler dạng catch-all** phủ thân method, sau đó `athrow` để ném lại **chính Throwable gốc**.

Ta thực sự biên dịch, chạy agent với `-Xverify:all`, gọi cả hai đường thoát và kiểm chứng instruction/exception table bằng `javap` và một công cụ Class-File API **độc lập**.

**Kết quả phải chứng minh:**

1. Một lời gọi bình thường vào `Calculator.evaluate(4)` trả **25**, được ghi nhận là `RETURN`.
2. `evaluate(-1)` ném `IllegalArgumentException` do code viết rõ; được ghi nhận là `THROW` và caller vẫn bắt đúng exception.
3. `evaluate(0)` ném `ArithmeticException` khi bytecode `idiv` thực thi; **không có lệnh `athrow` viết trong Java source tại nhánh này**, nhưng catch-all vẫn ghi nhận `THROW`.
4. Ba invocation cho **3 enter, 1 return, 2 throw**, không còn `ThreadLocal` frame đang chờ; tổng duration tính từ đồng hồ monotonic của JVM.
5. Bytecode **trước** instrumentation không có các hook; bản **sau** có đúng 1 `enter`, 1 `success`, 1 `failure` và 1 catch-all handler.
6. Thực thi với `java -Xverify:all -javaagent:...` thành công, đồng thời giá trị trả về và loại exception vẫn được giữ nguyên trong test.

**Giới hạn:** bài thí nghiệm chọn **một phương thức static trả `int`**, không phải constructor/native method. Mã đã kiểm thử này chưa phải framework để tự động instrument mọi class, mọi exception-handler layout hoặc mọi phiên bản JDK. Các điểm cần bổ sung cho production được giải thích riêng, không che giấu.

## 2. Vì sao “đếm RETURN” không đủ?

Xét method:

~~~java
public static int evaluate(int n) {
    if (n < 0) {
        throw new IllegalArgumentException("negative");
    }
    return 100 / n;
}
~~~

Đây là **một method Java minh họa**, sẽ có file đầy đủ tại mục 7. Ba invocation:

| Gọi | Đường thực thi | Kết quả |
| --- | --- | --- |
| `evaluate(4)` | `100 / 4` → `ireturn` | Trả về `25` |
| `evaluate(-1)` | Tạo exception → `athrow` | Ném `IllegalArgumentException` |
| `evaluate(0)` | `idiv` chia 0 → JVM phát exception | Ném `ArithmeticException` |

Nếu chỉ biến đổi `ReturnInstruction`:

~~~text
method entry -> start timer
...
khi thấy IRETURN -> record elapsed

evaluate(4)  -> được ghi nhận
evaluate(-1) -> không đi qua IRETURN
evaluate(0)  -> JVM ném tại IDIV, không đi qua IRETURN
~~~

Bộ đếm “đã vào method” tăng 3 nhưng “đã kết thúc” mới tăng 1. Nếu giữ start-time trên `ThreadLocal`, hai entry thất bại còn có thể **rò context**, làm duration của các lời gọi tiếp theo sai.

Cũng không đủ nếu chỉ đặt probe trước các instruction `ATHROW` có sẵn: ngoại lệ có thể phát sinh tại `idiv`, `getfield`, `invokevirtual`, truy cập mảng hoặc method con. **Exception handler bao phủ phạm vi code** là cơ chế thích hợp để bắt các trường hợp exception *thoát ra khỏi phạm vi method*, không cần dự đoán mọi opcode có thể phát lỗi.

### 2.1. “Throw” là thoát khỏi method, không phải cứ có `throw` là tính một lần lỗi

Một method có thể ném `IOException` rồi **bắt và xử lý** ngay trong chính nó, cuối cùng trả về thành công. Khi mục tiêu là **method-exit outcome**, không được tính exception đã được handle nội bộ thành một lần thoát lỗi.

~~~java
try {
    operation();
} catch (RecoverableException e) {
    recover();
}
return normalResult;
~~~

Đây là **pseudocode Java**, các phương thức chưa được khai báo. Outcome của method là `RETURN` nếu ngoại lệ đã được xử lý và method trả về bình thường. Muốn đúng semantics này, một catch-all được thêm sau các handlers hiện có phải tôn trọng **thứ tự/range của exception table**; không tùy tiện biến mọi exception nội bộ thành `THROW`.

### 2.2. Normal return cũng có nhiều opcode

Trong JVM, method có thể kết thúc bằng `RETURN` (void), `IRETURN` (int/boolean/byte/char/short), `LRETURN`, `FRETURN`, `DRETURN` hoặc `ARETURN`. JDK 24 Class-File API cung cấp kiểu `ReturnInstruction` để nhận diện nhóm này.

Lọc đúng **`ReturnInstruction`** tốt hơn cách tìm duy nhất chuỗi `"return"` trong source hoặc chỉ tìm `ARETURN`. Tuy nhiên, việc chèn hook trước một return có giá trị trên operand stack vẫn đòi hỏi stack effect của hook phù hợp. Bài chọn `success():void` **không có tham số**, nên lời gọi static không lấy hay thay đổi giá trị `int` đã chờ trên stack.

## 3. Mô hình đo: entry, success exit, exceptional exit

~~~text
   JVM định nghĩa Calculator.evaluate
             |
             v
      TimingProbe.enter()
      ghi startNano vào stack theo thread
             |
             v
       Thân method gốc
       /               \
   return                Throwable thoát ra
      |                         |
      v                         v
success()                 catch-all handler
  pop start                     |
  record elapsed                v
      |                    failure()
      v                      pop start
return value intact        record elapsed
                                  |
                                  v
                               athrow
                           cùng Throwable gốc
~~~

Tương đương gần đúng trong Java source (để **giải thích ngữ nghĩa**, **không** phải source mà transformer trực tiếp tạo bằng javac):

~~~java
TimingProbe.enter();
try {
    int value = originalEvaluate(n);
    TimingProbe.success();
    return value;
} catch (Throwable error) {
    TimingProbe.failure();
    throw error;
}
~~~

Đây là **pseudocode**: `originalEvaluate` không được khai báo trong file. Transformer ở mục 9 thực tế **giữ nguyên code elements của phương thức**, chèn hook trước `ireturn` và thêm một exception table handler.

Một lưu ý quan trọng: pseudocode trên đặt `success()` trong vùng `try`. Nếu chính helper `success()` ném lỗi, catch-all có thể gọi tiếp `failure()`, làm thay đổi outcome. Thí nghiệm sử dụng helper rất đơn giản và đã kiểm thử, **không phải cam kết helper bất khả lỗi**. Trong production nên thiết kế probe có bảo vệ fail-open, tránh để lỗi telemetry che mất lỗi nghiệp vụ hoặc gây đếm đôi.

## 4. Chọn nguồn thời gian và định nghĩa latency

Dùng `System.nanoTime()` để tính **elapsed time trong cùng JVM**:

~~~java
long start = System.nanoTime();
try {
    doWork();
} finally {
    long elapsedNanos = System.nanoTime() - start;
    record(elapsedNanos);
}
~~~

Đây là **mảnh code** giả định có `doWork` và `record`. `nanoTime` được thiết kế để so **chênh lệch thời gian**, không phải timestamp theo đồng hồ lịch. Không đổi `nanoTime` ra `Instant`, không so số nanoTime giữa các JVM/process.

Trong một invocation ngắn, `elapsedNanos` thường không âm; tài liệu JDK lưu ý phép trừ dạng trên có thể dùng khi khoảng thời gian cần đo nhỏ hơn giới hạn biểu diễn của signed `long`. Giá trị là **elapsed wall-clock/monotonic**, bao gồm thời gian method bị scheduler tạm dừng, chờ lock/I/O/GC và overhead của probe, **không phải CPU time thuần**.

| Chỉ số | Định nghĩa | Điều không suy ra |
| --- | --- | --- |
| Elapsed nanos | `nanoTime(exit) - nanoTime(entry)` | Không tự tách CPU, I/O hay lock |
| Method invocation count | Số lần vào method được instrument | Không tự đại diện số request toàn hệ thống |
| Success count | Số invocation rời method bằng return | Không nhất thiết là HTTP/business success |
| Throw count | Số invocation thoát ra ngoài bằng Throwable | Không đồng nghĩa số exception từng được tạo/bắt trong method |
| Duration sum | Tổng elapsed của các invocation đã hoàn thành | Không là wall-clock toàn process khi có concurrency/nesting |
| Time histogram | Phân bố duration theo bucket | Cần giới hạn cardinality và ràng buộc sampling |

Một method trả về bình thường vẫn có thể trả `null` hoặc mã lỗi nghiệp vụ. **Method-exit outcome** khác với ý nghĩa domain “thành công/thất bại”. Bài đếm `RETURN`/`THROW` theo **đường điều khiển JVM**; không tự phân loại HTTP 500 hoặc kết quả `false` thành `THROW`.

## 5. Vì sao dùng JDK 24 cho agent trong bài?

Java có `java.lang.instrument` từ lâu, nhưng từ **JDK 24**, `java.lang.classfile` được chuẩn hóa (JEP 484). API này cho phép parse, build và transform class-file bytes trực tiếp mà không cần ASM/Byte Buddy.

**Yêu cầu của thí nghiệm:**

| Thành phần | Phiên bản / điều kiện |
| --- | --- |
| Compile agent/app/verifier | **JDK 24** với `javac --release 24` |
| Chạy thử | JVM **JDK 24**, có `-javaagent` và `-Xverify:all` |
| Class-File API | `java.lang.classfile.*` trong `java.base` |
| Java agent API | `java.lang.instrument` trong `java.instrument` |
| Thư viện phụ thuộc | Không cần thư viện bytecode ngoài JDK |
| Cơ chế nạp | `premain` tại startup, chỉ transform **initial class definition** |
| Lớp đích | `demo/app/Calculator`, method `evaluate(int):int` |

JDK 17 hay JDK 21 **không có Class-File API chuẩn mang đúng package này**. Một ứng dụng đo thời gian thủ công bằng `try/finally` có thể biên dịch ở Java 17, nhưng **mã Java agent dùng `java.lang.classfile` trong bài cần JDK 24**.

`ClassFile.of().parse(byte[])` tạo một `ClassModel`; `ClassFile.transformClass(model, ClassTransform)` tạo mảng class bytes mới. `CodeTransform` xử lý từng `CodeElement`, trong đó `ReturnInstruction` biểu thị lệnh kết thúc bình thường. `CodeBuilder.exceptionCatchAll(start,end,handler)` thêm exception table entry bắt mọi Throwable thoát khỏi vùng xác định.

**Không phải bytecode transformation nào cũng được JVM chấp nhận**. Bản demo được kiểm thử dưới `-Xverify:all`, nhưng khi mở rộng sang code có handlers/stack maps/constructors/synchronized cần xác minh riêng.

## 6. Cấu trúc file của dự án

~~~text
method-time-agent/
  agent-src/demo/agent/
    TimingAgent.java
    TimingProbe.java
  app-src/demo/app/
    Calculator.java
    Main.java
  tool-src/
    VerifyTiming.java
  MANIFEST.MF
  agent-classes/       (do javac tạo)
  app-classes/         (do javac tạo)
  tool-classes/        (do javac tạo)
  timing-agent.jar     (do jar tạo)
  transformed/
    demo/app/Calculator.class  (bản dump chỉ dùng kiểm chứng)
~~~

**Trách nhiệm từng thành phần:**

- `Calculator`: method nghiệp vụ có một normal return, một explicit throw và một implicit throw.
- `Main`: gọi ba đường đi, bắt đúng hai exception ở caller, hiển thị counters của helper.
- `TimingProbe`: stack start times per thread, đo duration, phân loại `RETURN`/`THROW`, dọn `ThreadLocal` sau lần thoát cuối.
- `TimingAgent`: nhận `Instrumentation`, chèn entry/return/exception handler bằng JDK Class-File API.
- `VerifyTiming`: đọc **bản gốc và bản đã biến đổi** bằng chương trình riêng; xác nhận chính xác các invocation và catch-all entry.

File `transformed/...` chỉ được agent **dump** để dùng `javap` và verifier độc lập. JVM **không cần file dump** để load class: transformer trả trực tiếp `byte[]`. Không sao chép hành vi ghi đĩa đồng bộ trong callback sang production.

## 7. Mã ứng dụng: một normal return và hai kiểu exception

**Tệp `app-src/demo/app/Calculator.java`**

~~~java
package demo.app;

public final class Calculator {
    public static int evaluate(int n) {
        if (n < 0) throw new IllegalArgumentException("negative");
        return 100 / n;
    }
}
~~~

**Tệp `app-src/demo/app/Main.java`**

~~~java
package demo.app;
import demo.agent.TimingProbe;

public final class Main {
    public static void main(String[] args) {
        System.out.println("result=" + Calculator.evaluate(4));
        try {
            Calculator.evaluate(-1);
        } catch (IllegalArgumentException expected) {
            System.out.println("caught=" + expected.getClass().getSimpleName());
        }
        try {
            Calculator.evaluate(0);
        } catch (ArithmeticException expected) {
            System.out.println("caught=" + expected.getClass().getSimpleName());
        }
        TimingProbe.summary();
    }
}
~~~

Cả hai file này **không hề gọi `TimingProbe.enter/success/failure`**. `Main` chỉ đọc `summary()` để kiểm chứng kết quả sau khi gọi nghiệp vụ. Điều này giúp chứng minh điểm đo mới là do agent chèn.

`evaluate(-1)` xây một `IllegalArgumentException` và dùng `athrow`; `evaluate(0)` chạy `idiv` rồi **JVM tạo `ArithmeticException`**. Trường hợp thứ hai là phép thử quyết định: chỉ thêm hook trước `athrow` có sẵn sẽ **không** đủ để bắt đường thoát này.

## 8. Helper lưu start-time và đo thời gian đầy đủ

**Tệp `agent-src/demo/agent/TimingProbe.java`**

~~~java
package demo.agent;

import java.util.ArrayDeque;
import java.util.concurrent.atomic.AtomicLong;

public final class TimingProbe {
    private static final ThreadLocal<ArrayDeque<Long>> START =
            ThreadLocal.withInitial(ArrayDeque::new);
    private static final AtomicLong ENTERED = new AtomicLong();
    private static final AtomicLong RETURNED = new AtomicLong();
    private static final AtomicLong THROWN = new AtomicLong();
    private static final AtomicLong NANOS = new AtomicLong();

    public static void enter() {
        START.get().push(System.nanoTime());
        ENTERED.incrementAndGet();
    }

    public static void success() {
        finish(false);
    }

    public static void failure() {
        finish(true);
    }

    private static void finish(boolean failed) {
        ArrayDeque<Long> stack = START.get();
        long elapsed = System.nanoTime() - stack.pop();
        if (stack.isEmpty()) START.remove();
        NANOS.addAndGet(elapsed);
        if (failed) THROWN.incrementAndGet();
        else RETURNED.incrementAndGet();
        System.out.println("probe.exit="
                + (failed ? "THROW" : "RETURN"));
    }

    public static void summary() {
        System.out.println("probe.entered=" + ENTERED.get());
        System.out.println("probe.returned=" + RETURNED.get());
        System.out.println("probe.thrown=" + THROWN.get());
        System.out.println("probe.timeCaptured=" + (NANOS.get() > 0));
    }
}
~~~

### 8.1. Vì sao dùng `ThreadLocal<ArrayDeque<Long>>`?

Một `static long start` chung là **sai** khi nhiều thread gọi đồng thời; thread A có thể ghi đè timestamp của thread B. Một `ThreadLocal<Long>` khắc phục việc dùng chung giữa threads nhưng **chưa đủ** cho recursion và lồng nhau trong cùng thread: lời gọi con có thể ghi đè start của lời gọi cha.

Bài dùng **một stack riêng cho mỗi thread**:

~~~text
Thread T1:
  enter outer -> stack [startOuter]
  enter inner -> stack [startInner, startOuter]
  exit inner  -> pop startInner
  exit outer  -> pop startOuter
  stack empty -> ThreadLocal.remove()

Thread T2:
  có stack độc lập, không chạm dữ liệu T1
~~~

Đây là **sơ đồ nguyên tắc**, không phải trace trực tiếp của demo (demo không có nested calls). Nếu có recursion, mỗi invocation được instrument sẽ push/pop một frame, với điều kiện mỗi enter có đúng một exit và không có lỗi helper làm đứt stack.

### 8.2. Vì sao `remove()` khi stack rỗng?

Thread pool tái sử dụng thread giữa nhiều request. `ThreadLocal` không được dọn có thể giữ các object đã quá hạn, gây memory retention hoặc làm một request thấy context cũ. Khi frame cuối pop xong, `START.remove()` xóa giá trị khỏi thread hiện tại.

**Quan trọng:** `ThreadLocal` chỉ đúng với **cùng một thread** thực thi enter/exit. Nếu method trả về `CompletableFuture` rồi công việc tiếp tục trên thread khác, duration ở method boundary **không** tự đại diện end-to-end async operation. Cần context propagation và lifecycle khác.

### 8.3. Vì sao `AtomicLong`?

`AtomicLong` giữ counters và tổng nanoseconds an toàn khi nhiều thread gọi. Demo in giá trị xác định theo một thread. Trong ứng dụng tải rất cao, `LongAdder` có thể giảm contention cho counters, histogram thường hữu ích hơn một tổng; nhưng đọc nhiều `LongAdder.sum()` đồng thời **không** tạo snapshot nguyên tử.

`NANOS.get() > 0` trong stdout là phép xác nhận bài thử đã thu thập thời gian dương trên JVM test, **không** phải một SLO hay một giá trị duration chính xác áp dụng cho mọi máy. Tránh hardcode số nanoseconds thực tế vì OS scheduling/JIT/GC thay đổi qua từng lần chạy.

### 8.4. Chi phí và mức an toàn của helper

Helper ở đây in `System.out.println` cho mọi exit **chỉ vì mục đích quan sát**. Đây không phải giải pháp production: log đồng bộ có thể làm tail latency tăng, trigger class loading của logger, gây recursion và tắc nghẽn.

Ở môi trường thật cần:

- Check cờ enable/sampling trước khi tạo payload nặng.
- Không biến lỗi telemetry thành lỗi nghiệp vụ; đặc biệt tránh che mất original Throwable.
- Giới hạn bộ nhớ của queue/exporter và số label để tránh cardinality bùng nổ.
- Tránh instrument lại chính `TimingProbe`, agent, logger, exporter.
- Dùng duration histogram phù hợp thay vì in mỗi method call.

## 9. Transformer: tạo đúng ba hook và một catch-all handler

**Tệp `agent-src/demo/agent/TimingAgent.java`**, toàn bộ code đã biên dịch và chạy thành công trên JDK 24:

~~~java
package demo.agent;

import java.lang.classfile.*;
import java.lang.classfile.instruction.ReturnInstruction;
import java.lang.constant.ClassDesc;
import java.lang.constant.MethodTypeDesc;
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;
import java.nio.file.Files;
import java.nio.file.Path;

public final class TimingAgent {
    private static final ClassDesc PROBE =
            ClassDesc.of("demo.agent.TimingProbe");
    private static final MethodTypeDesc NO_ARGS_VOID =
            MethodTypeDesc.ofDescriptor("()V");

    public static void premain(String args, Instrumentation inst) {
        inst.addTransformer(new TimerTransformer(), false);
        System.out.println("agent=installed");
    }

    private static final class TimerTransformer
            implements ClassFileTransformer {
        @Override
        public byte[] transform(ClassLoader loader, String className,
                Class<?> redefining, ProtectionDomain domain, byte[] bytes) {
            if (!"demo/app/Calculator".equals(className)) return null;

            ClassFile cf = ClassFile.of();
            CodeTransform timer = CodeTransform.ofStateful(() ->
                    new CodeTransform() {
                Label from;
                Label to;
                Label handler;

                @Override
                public void atStart(CodeBuilder out) {
                    from = out.newLabel();
                    to = out.newLabel();
                    handler = out.newLabel();
                    out.invokestatic(PROBE, "enter", NO_ARGS_VOID);
                    out.labelBinding(from);
                }

                @Override
                public void accept(
                        CodeBuilder out, CodeElement element) {
                    if (element instanceof ReturnInstruction) {
                        out.invokestatic(PROBE, "success", NO_ARGS_VOID);
                    }
                    out.with(element);
                }

                @Override
                public void atEnd(CodeBuilder out) {
                    out.labelBinding(to);
                    out.labelBinding(handler);
                    out.invokestatic(PROBE, "failure", NO_ARGS_VOID);
                    out.athrow();
                    out.exceptionCatchAll(from, to, handler);
                }
            });

            byte[] transformed = cf.transformClass(cf.parse(bytes),
                    ClassTransform.transformingMethodBodies(
                        method -> method.methodName()
                                .equalsString("evaluate"),
                        timer));

            try {
                Path path = Path.of(
                        "transformed/demo/app/Calculator.class");
                Files.createDirectories(path.getParent());
                Files.write(path, transformed);
            } catch (java.io.IOException ex) {
                throw new RuntimeException(ex);
            }

            System.out.println("agent.transformed=" + className);
            return transformed;
        }
    }
}
~~~

### 9.1. `atStart`: mốc thời gian rồi bắt đầu vùng được bảo vệ

~~~java
out.invokestatic(PROBE, "enter", NO_ARGS_VOID);
out.labelBinding(from);
~~~

Đây là **mảnh code từ transformer**. `TimingProbe.enter()` chạy đầu method; sau đó label `from` đánh dấu **bắt đầu phạm vi catch-all**. Điều đó có nghĩa nếu **chính `enter()` ném lỗi**, exception đó không đi vào handler mà transform thêm. Bài không tuyên bố helper không thể lỗi; production cần cách xử lý phù hợp.

`ClassDesc.of("demo.agent.TimingProbe")` dùng **binary name dấu chấm**; callback `className` so sánh **internal name dấu slash** `demo/app/Calculator`. Không thay nhầm hai cú pháp.

### 9.2. `accept`: chèn trước mọi normal return, giữ code gốc

~~~java
if (element instanceof ReturnInstruction) {
    out.invokestatic(PROBE, "success", NO_ARGS_VOID);
}
out.with(element);
~~~

`ReturnInstruction` đại diện nhóm instruction `return` theo kiểu giá trị trả về. Trong demo method trả `int`, đó là `ireturn`. Lệnh `invokestatic` tới `success():()V` **không tiêu thụ tham số và không trả giá trị**, nên `int` đang nằm trên operand stack vẫn được `ireturn` sử dụng.

**Lưu ý:** đây là giải thích cho method demo và helper `()V` cụ thể. Nếu đổi helper thành `success(long)`, phải push start time lên stack đúng vị trí và kiểm tra stack-map frames. Nếu muốn truyền kết quả `int`, phải biết cách lưu/tải giá trị để giữ nguyên operand stack.

`out.with(element)` giữ toàn bộ code elements cũ. Nếu quên, transformer có thể xóa instruction và phá method. Nếu chỉ thêm `success` trước return mà không có catch-all, mọi invocation ném exception vẫn bị bỏ sót.

### 9.3. `atEnd`: tạo handler cho mọi exception thoát

~~~java
out.labelBinding(to);
out.labelBinding(handler);
out.invokestatic(PROBE, "failure", NO_ARGS_VOID);
out.athrow();
out.exceptionCatchAll(from, to, handler);
~~~

Đây là **mảnh code từ transformer**. Hai label `to`/`handler` xác định hết phạm vi code gốc và điểm vào handler. `exceptionCatchAll(from, to, handler)` tạo entry trong exception table với catch type **any**, thay vì chỉ bắt `IllegalArgumentException`.

Khi một Throwable từ thân method không được xử lý nội bộ thoát ra:

1. JVM đặt **Throwable đang bị ném** trên operand stack tại entry của handler.
2. `failure():()V` được gọi, không lấy Throwable khỏi stack.
3. `athrow` ném lại **cùng object Throwable**. Demo còn giữ đúng subtype `IllegalArgumentException` và `ArithmeticException` ở caller.

**Quan trọng:** handler này bắt được exception phát sinh từ `idiv`, không chỉ instruction `athrow` hiển thị trong class. Đây là lý do mục 7 dùng cả explicit và implicit exceptions.

### 9.4. Vì sao `CodeTransform.ofStateful`?

Ba label `from`, `to`, `handler` thuộc **một method body**. `CodeTransform.ofStateful(() -> new CodeTransform() {...})` tạo instance transform với state riêng cho mỗi traversal, không vô tình tái sử dụng labels giữa nhiều phương thức.

Ví dụ chỉ chọn một method, nhưng đây là mẫu đúng khi mở rộng. Không giữ các label trong một static field chia sẻ giữa những transformations đồng thời.

### 9.5. Scope thực nghiệm và điều không nên suy rộng

Transformer lọc theo `className=="demo/app/Calculator"` và `methodName()=="evaluate"`. Class demo có **một** `evaluate`, không có overload, constructor hay body native.

Trong agent thực tế cần lọc thêm descriptor chính xác, ví dụ `(I)I`, và kiểm tra method flags. Nếu method có exception handlers gốc, thiết kế phải giữ đúng thứ tự ưu tiên, labels/ranges, stack maps, exceptional execution paths. **Không** bừa chèn một catch-all lên trước handlers gốc, làm thay đổi semantics của những exception được method tự xử lý.

`Files.write` trong transformer là **test-only dump**; production nên loại bỏ I/O đồng bộ trong class loading. `transform` trả mảng bytes mới, không sửa mảng `classfileBuffer` được JVM giao.

## 10. Tạo manifest và biên dịch

**Tệp `MANIFEST.MF`**

~~~text
Manifest-Version: 1.0
Premain-Class: demo.agent.TimingAgent

~~~

Manifest có dòng trống kết thúc phần main attributes. Đúng tên class `demo.agent.TimingAgent`; JVM gọi `premain` trước application `main`.

**Từ thư mục `method-time-agent`, trên Windows PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force agent-classes, app-classes, tool-classes | Out-Null

javac --release 24 -d agent-classes agent-src/demo/agent/TimingAgent.java agent-src/demo/agent/TimingProbe.java

jar --create --file timing-agent.jar --manifest MANIFEST.MF -C agent-classes .

javac --release 24 -cp timing-agent.jar -d app-classes app-src/demo/app/Calculator.java app-src/demo/app/Main.java

java -cp "app-classes;timing-agent.jar" demo.app.Main

java -Xverify:all -javaagent:timing-agent.jar -cp "app-classes;timing-agent.jar" demo.app.Main
~~~

Lệnh thứ nhất tạo các thư mục; `javac` tạo `.class`; `jar` đóng toàn bộ agent và helper classes; ứng dụng cần `timing-agent.jar` trên classpath để đọc `TimingProbe.summary()`.

**Trên Bash/Linux/macOS:** lệnh tạo thư mục là `mkdir -p agent-classes app-classes tool-classes` và dấu phân tách classpath là `:`:

~~~bash
mkdir -p agent-classes app-classes tool-classes
javac --release 24 -d agent-classes \
  agent-src/demo/agent/TimingAgent.java \
  agent-src/demo/agent/TimingProbe.java
jar --create --file timing-agent.jar --manifest MANIFEST.MF \
  -C agent-classes .
javac --release 24 -cp timing-agent.jar -d app-classes \
  app-src/demo/app/Calculator.java app-src/demo/app/Main.java
java -cp "app-classes:timing-agent.jar" demo.app.Main
java -Xverify:all -javaagent:timing-agent.jar \
  -cp "app-classes:timing-agent.jar" demo.app.Main
~~~

Không sử dụng `--add-exports`/`--enable-preview` để “bật” Class-File API trong JDK 24: package chuẩn `java.lang.classfile` đã được tích hợp. Cũng không cần `Can-Retransform-Classes` vì bài chỉ áp dụng initial-load transformer `addTransformer(..., false)`, không retransform class đã load.

### 10.1. Tại sao cần hai lần chạy?

- **Không có `-javaagent`:** lớp `Calculator` chạy nguyên bản; `Probe` không nhận entry/exit vì source `Calculator` chưa có lời gọi helper.
- **Có `-javaagent`:** JVM gọi `premain` trước khi `Calculator` load, transformer trả class bytes đã thêm hooks và exception table.
- `-Xverify:all` yêu cầu JVM kiểm tra bytecode một cách nghiêm ngặt hơn trong phép thử, hữu ích để phát hiện output không hợp lệ.
- Việc chạy ở **hai tiến trình JVM riêng** tránh trạng thái class đã load/đã transform của lần thử trước. Không thể “unload Calculator rồi load lại” tùy ý bằng một lệnh `Class.forName` trong cùng loader.

## 11. Kết quả thực thi chính xác trên Zulu/OpenJDK 24.0.2

### 11.1. Baseline không có agent

~~~text
result=25
caught=IllegalArgumentException
caught=ArithmeticException
probe.entered=0
probe.returned=0
probe.thrown=0
probe.timeCaptured=false
~~~

Đây là output của lệnh `java -cp ... demo.app.Main`, có helper trong classpath nhưng không có transformer. `Calculator.evaluate` vẫn trả đúng và ném đúng hai exception; các counter bằng **0**.

### 11.2. Khi có agent

~~~text
agent=installed
agent.transformed=demo/app/Calculator
probe.exit=RETURN
result=25
probe.exit=THROW
caught=IllegalArgumentException
probe.exit=THROW
caught=ArithmeticException
probe.entered=3
probe.returned=1
probe.thrown=2
probe.timeCaptured=true
~~~

**Đã kiểm thử:** compile với `javac --release 24`, đóng JAR agent, chạy `java -Xverify:all -javaagent:...` trên Zulu/OpenJDK **24.0.2**. Các dòng stdout ở trên khớp đúng kết quả thí nghiệm.

Phân tích:

1. `agent=installed` xuất hiện trước các lời gọi nghiệp vụ do `premain` chạy ở startup.
2. `agent.transformed=demo/app/Calculator` cho thấy transformer đã chạm đúng class, không phải helper/logger.
3. `probe.exit=RETURN` xuất hiện **trước** `result=25`, bởi code inside `evaluate` gọi helper trước khi trả về caller.
4. `probe.exit=THROW` trước `caught=IllegalArgumentException` nghĩa helper ở exception handler chạy **trước khi Throwable được ném lại** đến caller.
5. `probe.exit=THROW` trước `caught=ArithmeticException` chứng minh catch-all xử lý cả exception từ `idiv`.
6. `entered=3`, `returned=1`, `thrown=2` và `timeCaptured=true`: cả ba invocation có entry/exit theo đường đi tương ứng.

**Không hardcode duration cụ thể** trong stdout. Khi chạy lại, số `elapsed nanoseconds` thay đổi. Boolean `timeCaptured=true` là output của bài thử trên môi trường này, không là lời hứa thời lượng >0 cho từng method trên mọi hệ điều hành/timer resolution.

### 11.3. Bất biến kế toán

Sau khi mọi invocation kết thúc bình thường ở mức Java control flow:

~~~text
entered = returned + thrown
3       = 1        + 2
~~~

Bất biến này đúng trong **demo một thread**, nơi mọi method exit đi qua helper hoàn chỉnh. Với production, lỗi helper, process crash, `System.exit`/`Runtime.halt`, frame đang chạy, lấy mẫu, queue drop hoặc races khi đọc nhiều counters có thể khiến quan sát tại một thời điểm không khớp.

Không dùng equality này để tuyên bố “không có mất telemetry end-to-end”: bộ đếm đo trong helper vẫn có thể tăng dù exporter gửi dữ liệu thất bại. **Counter của instrumented method** và **số record backend nhận được** phải được theo dõi riêng.

## 12. `javap`: bytecode trả về và exception table sau biến đổi

Sau khi chạy agent, bản dump test nằm tại:

~~~text
transformed/demo/app/Calculator.class
~~~

Chạy:

~~~bash
javap -c -p -classpath app-classes demo.app.Calculator
javap -c -p -classpath transformed demo.app.Calculator
~~~

**Trích đoạn `evaluate` sau biến đổi**, đã xác minh:

~~~text
public static int evaluate(int);
  Code:
     0: invokestatic  #27   // Method demo/agent/TimingProbe.enter:()V
     3: iload_0
     4: ifge          17
     7: new           #7    // class java/lang/IllegalArgumentException
    10: dup
    11: ldc           #9    // String negative
    13: invokespecial #11  // Method ...<init>:(Ljava/lang/String;)V
    16: athrow
    17: bipush        100
    19: iload_0
    20: idiv
    21: invokestatic  #30   // Method demo/agent/TimingProbe.success:()V
    24: ireturn
    25: invokestatic  #33   // Method demo/agent/TimingProbe.failure:()V
    28: athrow
  Exception table:
     from    to  target type
        3    25    25   any
~~~

Một số comment dài của `javap` đã được lược để dễ đọc; **opcodes, offsets và exception table** được giữ theo lần test. Constant-pool indexes `#27/#30/#33` là chi tiết compiler/transformer của lần build, **không phải giá trị phải hardcode** khi viết verifier đa môi trường.

Đọc kết quả:

- Offset **0**: lời gọi `enter` được thêm trước instruction gốc.
- Offset **21**: lời gọi `success` được chèn trước `ireturn`.
- Offset **25**: handler mới gọi `failure`.
- Offset **28**: `athrow` ném lại Throwable vừa bị bắt.
- Exception table: vùng từ **3 (inclusive)** đến **25 (exclusive)**; handler bắt mọi kiểu Throwable tại offset **25**.
- `idiv` ở offset 20 nằm trong vùng catch-all. Nếu chia 0, JVM chuyển điều khiển vào handler dù instruction tại 20 **không phải `athrow`**.

**Hai lưu ý quan trọng:** vùng catch-all bắt đầu **sau** `enter()`; ngoại lệ của chính entry hook không bị handler này bao phủ. Nó cũng bao gồm `success()` được chèn trước return; do đó một lỗi từ success hook có thể đi qua handler và gây logic đo đạc khác ngoài dự kiến. Đây là lý do helper production phải có fail-open/error isolation và test exception semantics, không chỉ “build thành công”.

## 13. Verifier độc lập bằng Class-File API

Kiểm chứng của chính transformer hoặc log stdout là hữu ích nhưng chưa đủ. Ta tạo **chương trình khác** đọc cả hai tệp `.class` và tự thống kê invocation/exception handlers.

**Tệp `tool-src/VerifyTiming.java`**

~~~java
import java.lang.classfile.*;
import java.lang.classfile.instruction.InvokeInstruction;
import java.lang.constant.ClassDesc;
import java.nio.file.Files;
import java.nio.file.Path;

public final class VerifyTiming {
    private static final ClassDesc PROBE =
            ClassDesc.of("demo.agent.TimingProbe");

    private static void verify(String label, Path path) throws Exception {
        ClassModel model = ClassFile.of()
                .parse(Files.readAllBytes(path));
        MethodModel method = model.methods().stream()
                .filter(m -> m.methodName().equalsString("evaluate"))
                .findFirst().orElseThrow();
        CodeModel code = method.code().orElseThrow();

        for (String name : new String[] {
                "enter", "success", "failure"}) {
            long n = code.elementStream()
                    .filter(e -> e instanceof InvokeInstruction call
                            && call.opcode() == Opcode.INVOKESTATIC
                            && call.owner().asSymbol().equals(PROBE)
                            && call.name().equalsString(name)
                            && call.typeSymbol()
                                    .descriptorString().equals("()V"))
                    .count();
            System.out.println(label + "." + name + "=" + n);
        }

        long all = code.exceptionHandlers().stream()
                .filter(e -> e.catchType().isEmpty()).count();
        System.out.println(label + ".catchAll=" + all);
    }

    public static void main(String[] args) throws Exception {
        verify("original",
                Path.of("app-classes/demo/app/Calculator.class"));
        verify("transformed",
                Path.of("transformed/demo/app/Calculator.class"));
    }
}
~~~

**Lệnh chạy sau khi đã chạy agent và có bản dump:**

~~~bash
javac --release 24 -d tool-classes tool-src/VerifyTiming.java
java -cp tool-classes VerifyTiming
~~~

**Stdout chính xác đã kiểm thử:**

~~~text
original.enter=0
original.success=0
original.failure=0
original.catchAll=0
transformed.enter=1
transformed.success=1
transformed.failure=1
transformed.catchAll=1
~~~

Chương trình kiểm tra **opcode, owner class, method name và descriptor `()V`**, không chỉ tìm chuỗi `"TimingProbe"` trong constant pool. Một class có thể chứa tên helper dưới dạng metadata/string mà không có instruction thực sự gọi helper. Với `exceptionHandlers()`, `catchType().isEmpty()` nhận diện catch-all entry, không đồng nhất với một handler chỉ bắt một exception subtype cụ thể.

**Giới hạn kiểm chứng:** đây là structural assertion. Nó không đo duration thực tế hoặc chứng minh có đúng một event cho mọi JVM failure scenario; phần thực thi `-Xverify:all` và test normal/error paths là tầng bổ sung.

## 14. Kiểm tra đúng loại exception và bảo toàn semantics

Một agent đo thời gian không nên thay đổi nghĩa nghiệp vụ. Trong demo:

~~~text
Before agent:
  evaluate(4)  -> int 25
  evaluate(-1) -> IllegalArgumentException
  evaluate(0)  -> ArithmeticException

With agent:
  evaluate(4)  -> int 25 + RETURN record
  evaluate(-1) -> IllegalArgumentException + THROW record
  evaluate(0)  -> ArithmeticException + THROW record
~~~

Đây là các hành vi **đã thử**, không phải suy ra từ việc classfile parse thành công. `athrow` trong handler dùng lại Throwable đang nằm trên operand stack, nên không chủ động dựng một exception khác.

### 14.1. Vì sao không nên chỉ catch `Exception`?

`catch (Exception)` bao phủ nhiều checked/unchecked exceptions nhưng **không bao phủ mọi `Error`**. Nếu mục tiêu là đo method thoát bằng bất kỳ `Throwable` nào, catch-all exception table của JVM (`any`) phù hợp hơn.

Tuy vậy, việc **ghi nhận** một `Error` trong helper không đồng nghĩa **được nuốt nó**. Agent phải tránh chuyển `OutOfMemoryError` hay `StackOverflowError` thành return thành công. Hãy giữ nguyên Throwable gốc và để JVM/caller xử lý theo semantics thông thường, nếu môi trường còn đủ tài nguyên.

### 14.2. Vì sao throw trong method con cũng được tính?

Giả sử:

~~~java
public static int parent() {
    return dependency.compute();
}
~~~

Đây là **mảnh code** có dependency chưa định nghĩa. Nếu `compute()` ném Throwable mà `parent` **không bắt**, ngoại lệ thoát qua method boundary của `parent`; catch-all của `parent` sẽ ghi `THROW`. Nếu `parent` bắt rồi trả giá trị, `parent` được ghi `RETURN`.

Nếu **cả parent lẫn child** được instrument, một lỗi lan từ child sang parent có thể tạo **hai method-exit THROW records**. Đây là đúng khi đơn vị đo là **invocation** của từng method, nhưng không phải “hai lỗi nghiệp vụ độc lập”. Phân biệt **exception object**, **throw propagation** và **method invocation outcome**.

## 15. Kỹ thuật stack/time an toàn khi lồng nhau và đệ quy

Một stack `ThreadLocal` giúp tách các invocation trong cùng thread:

~~~text
T1: enter outer at 100
T1: enter inner at 130
T1: exit inner at 145 (duration 15)
T1: exit outer at 190 (duration 90)

Tổng inclusive durations = 105,
không phải wall-clock 90 của luồng T1.
~~~

Đây là **ví dụ số liệu minh họa**, không phải nanoTime thực tế. Tổng thời gian inclusive của các methods lồng nhau có thể **đếm trùng** khoảng inner. Muốn **exclusive time**, cần một cơ chế khác trừ thời gian children hoặc tích lũy segments khi nested calls bắt đầu/kết thúc.

**Trường hợp recursion:** mỗi lần đệ quy tạo frame riêng, cùng method name nhưng khác invocation. Nếu chỉ lưu một `ThreadLocal<Long>`, start của outer có thể bị inner ghi đè. Vì vậy helper dùng `ArrayDeque<Long>`.

**Trường hợp async:** `CompletableFuture`, thread pool, reactive pipeline và callbacks có thể chuyển thread. `ThreadLocal` chỉ mô tả **Java method call boundary trên thread hiện tại**; nếu method trả Future trước khi computation xong, thời gian đo dừng lúc trả Future, không phải lúc Future complete. Muốn latency end-to-end cần gắn context vào lifecycle của operation bất đồng bộ, không dùng per-thread method timer rồi gán nhãn “tổng thời gian request”.

**Trường hợp exception làm lệch stack:** nếu hook success/failure không chạy, một frame có thể còn sót. Đoạn `START.remove()` khi stack rỗng không thể tự dọn một frame chưa bao giờ pop. Điều này đòi kiểm thử mọi exit path và guard cho các sự cố helper trong production.

## 16. Hạn chế của ví dụ và những method cần xử lý đặc biệt

| Dạng method | Tại sao không áp dụng nguyên xi? | Kiểm tra cần thiết |
| --- | --- | --- |
| `public static int evaluate(int)` đơn giản | **Demo đã thử**, một `IRETURN` và một catch-all | Cả return, explicit/implicit throws, verifier |
| `void`/`long`/`double`/object return | Opcode return và giá trị trên stack khác | `ReturnInstruction` đúng, helper không phá stack |
| `<init>` constructor | `this` chưa khởi tạo, verifier chặt | Không chèn arbitrary helper trước super/this init; chọn insertion point |
| `<clinit>` | Class initialization order, helper có thể load thêm class | Guard reentrancy và circular initialization |
| `native`/`abstract` | Không có `Code` trong chính method | Instrument Java caller/wrapper hoặc công cụ native/JVMTI |
| Synchronized method/block | Giữ monitor, exception flow và overhead | Không làm blocking I/O, giữ nguyên monitor semantics |
| Method có nhiều catch/finally | Thứ tự exception table/ranges ảnh hưởng ý nghĩa | Test caught vs uncaught, propagation, labels/stack maps |
| Multiple returns/overloads | Matcher theo tên có thể chọn quá rộng | Lọc descriptor, test mọi return opcode |
| Method có invokedynamic/lambda | Call stack và class loading thêm phức tạp | Test bootstrap/class visibility |
| Bridge/synthetic | Có thể tạo double counting | Hiểu cờ method và mục đích sampling |
| Các phương thức được gọi cực thường xuyên | Probe overhead cao | Sampling, bounded queue, low-allocation helper |
| Instrumented JDK classes | Agent helper có thể gây recursion/circularity | Exclude hoặc thiết kế bootstrap bridge cực nhỏ |
| Class đã loaded | Initial-load callback không chạy lại | `retransformClasses` có capability/giới hạn và idempotence |
| Asynchronous method | Return chỉ phản ánh Future được trả, không phải completion | Đo completion stage riêng |
| Error từ chính helper | Có thể che exception/đếm đôi/sai balance | Helper fail-open và cô lập failure paths |

### 16.1. Một rủi ro thật: helper ném exception ở success path

Trong transformer demo, `TimingProbe.success()` nằm trong vùng catch-all phủ cả thân method. Nếu `success()` ném, handler `failure()` cũng có thể chạy. Hệ quả là **một invocation có thể ghi cả RETURN và THROW hoặc ghi sai thời gian**, đồng thời thay đổi return/exception mà caller thấy.

Một thiết kế production cần xem xét:

- Không cho collector/logging failures escape khỏi probe.
- Tách vùng được bảo vệ của **business code** khỏi vùng hook khi có thể, dùng labels và branches đúng JVM rules.
- Dùng guard chống recursion; tránh allocate quá nhiều ngay cả trong error path.
- Không bắt `Throwable` rồi âm thầm nuốt mọi lỗi không phân biệt điều kiện, đặc biệt các JVM critical errors.
- Thêm unit tests cố tình làm recorder/exporter throw, để xác định fail-open policy và bảo toàn exception gốc.
- Đặt các counters `activeScope`, `missingExit` và `doubleFinish` trong bộ chẩn đoán có kiểm soát.

**Không tuyên bố `-Xverify:all` chứng minh hành vi production hoàn hảo**. Verifier xác nhận bytecode hợp lệ theo luật JVM trên test input; semantic invariants cần được kiểm thử và thiết kế riêng.

## 17. Chi phí instrumentation và cách xử lý khi tải cao

Đường đo thực tế bao gồm:

~~~text
entry hook:
  ThreadLocal lookup + ArrayDeque.push + nanoTime + atomic count

exit hook:
  nanoTime + ArrayDeque.pop + ThreadLocal.remove nếu hết
  + atomic count + ghi record/export
~~~

Trong ví dụ, `println` có thể chiếm thời gian lớn và làm kết quả duration khác xa chi phí nghiệp vụ thuần. Đo method “không instrument” và “instrument” bằng benchmark phù hợp, có warmup JIT/GC, concurrency và sample size. Không dùng một lượt chạy demo rồi công bố overhead nanoseconds cố định.

Nếu sampling:

- **Quyết định một lần ở entry** rồi lưu quyết định vào frame; không sample độc lập ở return và throw.
- Giữ sự cân bằng push/pop ngay cả khi invocation không được chọn để record; tốt hơn có một token/frame chỉ rõ `sampled`.
- Nếu dropped do queue full, phân biệt `sampledOut` (chủ động) với `queueDropped` (quá tải) và `exportFailed`.
- Dùng queue bounded và `offer` fail-open trên hot path thay vì `put` có thể block vô hạn; có quota cho payload, retry và shutdown.
- Giữ bộ đếm tổng invocation/failures ở vị trí không phụ thuộc vào raw trace sample nếu cần metrics chính xác.

Một ngoại lệ nghiệp vụ có thể rất hiếm và quan trọng; nếu chỉ head sample 1% thì **không bảo đảm** sẽ giữ mọi lỗi. Muốn ưu tiên errors cần tail sampling hoặc một error-summary channel có giới hạn. Đừng nhận định “lấy mẫu không ảnh hưởng error rate” nếu error rate được tính từ các sampled traces đã bị drop.

### 17.1. Thời gian của helper và thời gian của method

`enter` được gọi **trước** method instruction gốc. `success` được gọi **trước** `ireturn`, nên duration đo bao gồm phần code nghiệp vụ cho tới hook exit, nhưng có thể chưa bao gồm overhead của chính exit hook sau khi lấy `nanoTime`; thời điểm mốc được chụp ở đầu `finish` sau khi gọi helper.

`failure` chạy khi control chuyển vào handler mới, tức sau lúc exception đã được tạo/phát hiện/đi qua các handlers nội bộ. Do đó thời gian thất bại có thể bao gồm một phần exception dispatch. **Định nghĩa đo** phải ghi rõ “elapsed từ entry hook đến exit hook” thay vì “CPU time chính xác của method gốc không overhead”.

## 18. Troubleshooting: từ biểu hiện đến nguyên nhân

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| `package java.lang.classfile does not exist` | Dùng javac trước JDK 24 | `java -version`/`javac -version`, chọn JDK 24 |
| `ClassNotFoundException`/agent premain không chạy | Manifest, JAR/classpath sai | `jar tf timing-agent.jar`, xem `Premain-Class` |
| Không có dòng `agent.transformed` | Target được load quá sớm, matcher internal name sai | Đăng ký trong premain, tên `demo/app/Calculator` |
| `helper.entered=0` dù có agent | Transformer trả null/bị lỗi hoặc không match method | Inspect class bytes/JVM logs, thêm verifier |
| `returned=1` nhưng `thrown=0` dù app có lỗi | Chỉ chèn trước ReturnInstruction, chưa có catch-all | Xem `Exception table` và `failure`/`athrow` |
| `NullPointerException`/`NoSuchMethodError` trong helper | Descriptor/loader visibility sai | Đối chiếu `ClassDesc`/`()V`, classpath |
| `VerifyError` | Stack/handler labels, StackMapTable hoặc type flow sai | `-Xverify:all`, `javap -v`, thu nhỏ method test |
| `ClassFormatError` | Class-file bytes bị phá/attribute không hợp lệ | Parse output bằng Class-File API, không mutate input |
| `ArrayDeque.pop` gặp empty | Exit hook không có enter tương ứng hoặc double finish | Kiểm tra coverage, ThreadLocal nesting, error path |
| Một exception trở thành loại khác | Helper đã ném và che Throwable nghiệp vụ | Guard exit hook, giữ nguyên original exception |
| Counter enter/exit không cân bằng giữa lúc đang chạy | Invocation in-flight, chụp snapshot không đồng bộ | Đợi quiescence hoặc dùng snapshot phù hợp |
| Tổng elapsed quá lớn khi recursion | Inclusive duration cộng cả child frames | Muốn exclusive time phải trừ child time |
| Chỉ đo lúc trả `CompletableFuture` | Đang đo method boundary, không phải async completion | Instrument completion callback với context |
| File `transformed/...` không xuất hiện | Transformer chưa match hoặc không thể ghi dump | Dump chỉ phục vụ test, kiểm tra working directory |
| Chạy nhiều lần thấy mất/nhân đôi hooks | Retransform/redefine hoặc nhiều transformer | Idempotence, filter, theo dõi registration |
| App chậm rõ sau khi bật agent | Logging/collector đồng bộ, sampling/quota chưa đúng | Bỏ stdout trong hook, benchmark và bounded exporter |

### 18.1. Class-File API và verifier là hai lớp kiểm thử khác nhau

`ClassFile.of().parse(bytes)` cho phép quan sát cấu trúc. Vì parser có thể **lazy**, việc parse thành công không đồng nghĩa toàn bộ attributes/bytecode luôn hợp lệ. `java -Xverify:all` kiểm tra class khi JVM load; integration tests mới cho thấy exception behavior và return values trên các input cụ thể.

Một bộ QA đúng nên có:

1. Structural checks (số invoke instructions, opcode/owner/descriptor, catch-all entry).
2. JVM bytecode verification/load.
3. Runtime normal return test.
4. Runtime explicit throw test.
5. Runtime implicit exception test.
6. Tests khi helper có sự cố và khi class có handlers/branches phức tạp.
7. Concurrency/nesting/error-rate/performance tests.

## 19. Checklist thực hành

- [ ] JDK 24 thực sự được dùng cho cả `javac` và `java`.
- [ ] Agent được chạy bằng `-javaagent`; manifest có `Premain-Class` đúng.
- [ ] Matcher chỉ chọn `demo/app/Calculator` và method `evaluate`.
- [ ] `enter()` được chèn trước instruction gốc.
- [ ] `success()` được chèn trước `ReturnInstruction`.
- [ ] Catch-all handler có phạm vi phù hợp, gọi `failure()` rồi `athrow`.
- [ ] `out.with(element)` vẫn giữ mọi code element của method gốc.
- [ ] `CodeTransform.ofStateful` cấp labels/state riêng cho mỗi method traversal.
- [ ] Mảng `classfileBuffer` đầu vào không bị sửa tại chỗ.
- [ ] Baseline không agent cho 0 probe calls.
- [ ] With agent: `evaluate(4) == 25`.
- [ ] With agent: caller còn bắt đúng `IllegalArgumentException`.
- [ ] With agent: caller còn bắt đúng `ArithmeticException` từ `idiv`.
- [ ] `entered=3`, `returned=1`, `thrown=2` trong demo.
- [ ] `javap` hiện `invokestatic` mới trước `ireturn` và exception table bắt `any`.
- [ ] `VerifyTiming` đọc hai tệp class và xác minh 0→1 cho cả ba hooks và catch-all.
- [ ] `-Xverify:all` chạy thành công.
- [ ] Không dùng giá trị nanoseconds cố định làm assertion.
- [ ] Với production, thêm fail-open, kiểm soát helper throw và multi-loader/JPMS.
- [ ] Với method khác, thêm descriptor filter, native/constructor/exception handler/async tests.
- [ ] Loại trừ agent/helper/logger/exporter khỏi instrumentation.
- [ ] Không ghi tệp dump hoặc in mọi invocation trong callback/hot path ở production.

## 20. Câu hỏi tự kiểm tra

1. Vì sao chỉ chèn hook trước `IRETURN` bỏ sót `evaluate(-1)` và `evaluate(0)`?
2. `evaluate(0)` có instruction `athrow` tại vị trí chia 0 không? JVM tạo exception ở opcode nào?
3. `ReturnInstruction` bao phủ các kiểu return nào?
4. Vì sao `TimingProbe.success()` có descriptor `()V` trong ví dụ?
5. `exceptionCatchAll(from,to,handler)` thêm cấu trúc gì vào class file?
6. Vì sao handler không được phép nuốt Throwable gốc rồi trả giá trị giả?
7. Vì sao exception được method tự catch rồi xử lý không nên tính là method-level `THROW`?
8. Khi `success()` của helper tự ném, handler demo có thể ghi nhận sai những gì?
9. Vì sao thời gian đo bằng `System.nanoTime()` không nên dùng làm absolute timestamp?
10. Vì sao trong recursion cần stack thay vì một `ThreadLocal<Long>` duy nhất?
11. Vì sao tổng inclusive time của các methods nested có thể lớn hơn elapsed time của thread?
12. Vì sao latency của method trả `CompletableFuture` không đồng nghĩa thời gian hoàn tất tác vụ async?
13. Ý nghĩa của `java -Xverify:all` và giới hạn của JVM verifier là gì?
14. `javap` xác nhận instruction/exception table mới nào?
15. Tại sao kiểm tra độc lập `original.enter=0`, `transformed.enter=1` mạnh hơn chỉ đọc log transformer?
16. Vì sao bộ đếm `entered=returned+thrown` không phải chứng cứ exporter không mất dữ liệu?
17. Vì sao agent không nên instrument chính logger và helper của mình?
18. Tại sao JDK 17 không biên dịch nguyên văn agent `java.lang.classfile` của bài?
19. Cần lọc descriptor thế nào nếu `Calculator` có nhiều overload `evaluate`?
20. Bạn sẽ kiểm thử gì thêm trước khi triển khai agent đo duration trên method có nhiều try/catch/finally?

**Ghi nhớ:** Để đo **cả đường trả về bình thường và đường ném ngoại lệ**, instrumentation phải theo dõi **mọi normal return** **và** một **exceptional-exit handler** bao phủ code cần đo. Chỉ bắt `ATHROW` explicit không đủ vì JVM có thể ném exception từ các opcode khác. Trong thí nghiệm JDK 24, Class-File API tạo ba helper calls và một catch-all entry; `javap`, verifier độc lập và JVM `-Xverify:all` xác nhận 1 return và 2 throw được ghi nhận, còn kết quả nghiệp vụ giữ nguyên. Khi triển khai thật, cần bổ sung guard cho lỗi helper, class-loader/module visibility, tính nhất quán nested/async, sampling, overload và giới hạn tài nguyên.

### Tài liệu chính thức

- [JDK 24 — java.lang.classfile package](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/package-summary.html)
- [JDK 24 — CodeTransform](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/CodeTransform.html)
- [JDK 24 — CodeBuilder: exceptionCatchAll và invokestatic](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/CodeBuilder.html)
- [JDK 24 — ReturnInstruction](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/instruction/ReturnInstruction.html)
- [JDK 24 — ExceptionCatch](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/instruction/ExceptionCatch.html)
- [JDK 24 — ClassFile / ClassTransform](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassFile.html)
- [JDK 24 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/24/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html)
- [Java 17+ — System.nanoTime](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/System.html#nanoTime())
- [JEP 484 — Class-File API JDK 24](https://openjdk.org/jeps/484)
